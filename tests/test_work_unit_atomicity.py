"""Fault injection at the SQLite state/evidence transaction boundary."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from os29.store import Store
from os29.work_units import WorkUnitService

WORK_ID = "atomicity-regression"


def create(service: WorkUnitService) -> dict:
    return service.create(
        work_id=WORK_ID,
        project="public-test",
        objective="atomicity",
        owner_agent="agent-a",
        allowed_scope=[],
        current_state={"phase": "before"},
        known_good=[],
        known_bad=[],
        open_issues=[],
        next_steps=["verify"],
        context_refs=[],
    )


def reject_event(database: Path, kind: str) -> None:
    # The kind is supplied only by the fixed parameter list below.
    with sqlite3.connect(database) as connection:
        connection.execute(
            f"""CREATE TRIGGER reject_transition BEFORE INSERT ON trace_events
            WHEN NEW.kind = '{kind}'
            BEGIN SELECT RAISE(ABORT, 'injected evidence failure'); END"""
        )


@pytest.mark.parametrize(
    "operation,kind",
    [
        ("create", "work_unit.created"),
        ("checkpoint", "work_unit.checkpoint"),
        ("handoff", "work_unit.handoff"),
        ("complete", "work_unit.completed"),
        ("fail", "work_unit.blocked"),
    ],
)
def test_state_and_evidence_rollback_together(tmp_path, operation, kind):
    database = tmp_path / "isolated.db"
    store = Store(database)
    service = WorkUnitService(store)
    if operation != "create":
        create(service)
    if operation == "complete":
        service.record_evidence_receipt(
            work_id=WORK_ID,
            actor_agent="agent-a",
            action="test",
            outcome="success",
            evidence={
                "command": "test",
                "exit_code": 0,
                "stdout": "synthetic test receipt",
            },
            next_action="complete",
        )
    before = store.get_capsule(WORK_ID)
    events = store.list_trace(WORK_ID)
    reject_event(database, kind)
    with pytest.raises(sqlite3.IntegrityError, match="injected evidence failure"):
        if operation == "create":
            create(service)
        elif operation == "checkpoint":
            service.checkpoint(
                work_id=WORK_ID,
                actor_agent="agent-a",
                expected_revision=1,
                current_state={"phase": "after"},
                next_steps=["resume"],
                idempotency_key="retry",
            )
        elif operation == "handoff":
            service.handoff(
                work_id=WORK_ID,
                from_agent="agent-a",
                to_agent="agent-b",
                summary="test",
                next_action="resume",
            )
        elif operation == "complete":
            service.complete(work_id=WORK_ID, actor_agent="agent-a", expected_revision=1)
        else:
            service.fail(
                work_id=WORK_ID,
                actor_agent="agent-a",
                expected_revision=1,
                reason="test failure",
            )
    reopened = Store(database)
    assert reopened.get_capsule(WORK_ID) == before
    assert reopened.list_trace(WORK_ID) == events


def test_abrupt_exit_before_commit_rolls_back_state_and_evidence(tmp_path):
    import subprocess
    import sys

    database = tmp_path / "crash.db"
    service = WorkUnitService(Store(database))
    create(service)
    child = r"""
import os
import sys
from os29.store import Store
from os29.work_units import WorkUnitService

store = Store(sys.argv[1])
original = store._insert_event
def crash_after_insert(connection, event):
    original(connection, event)
    os._exit(23)
store._insert_event = crash_after_insert
WorkUnitService(store).checkpoint(
    work_id="atomicity-regression", actor_agent="agent-a",
    expected_revision=1, current_state={"phase": "crash"},
    next_steps=["resume"], idempotency_key="crash-checkpoint",
)
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(database)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 23, result.stderr
    recovered = WorkUnitService(Store(database))
    assert recovered.get(work_id=WORK_ID)["revision"] == 1
    assert recovered.get(work_id=WORK_ID)["current_state"] == {"phase": "before"}
    assert [event["kind"] for event in recovered.store.list_trace(WORK_ID)] == ["work_unit.created"]
    resumed = recovered.checkpoint(
        work_id=WORK_ID,
        actor_agent="agent-a",
        expected_revision=1,
        current_state={"phase": "recovered"},
        next_steps=["verify"],
        idempotency_key="crash-checkpoint",
    )
    assert resumed["revision"] == 2
    assert recovered.store.list_trace(WORK_ID)[-1]["event_id"] == resumed["event_id"]
    assert recovered.store.verify_work_unit(WORK_ID)["valid"]


def test_ten_independent_writers_preserve_all_revisions(tmp_path):
    import subprocess
    import sys

    database = tmp_path / "concurrent.db"
    start = tmp_path / "start"
    create(WorkUnitService(Store(database)))
    child = r"""
import sys
import time
from pathlib import Path
from os29.store import Store
from os29.work_units import WorkUnitService

service = WorkUnitService(Store(sys.argv[1]))
gate = Path(sys.argv[2])
agent = sys.argv[3]
deadline = time.monotonic() + 30
while not gate.exists():
    if time.monotonic() > deadline:
        raise TimeoutError("start barrier")
    time.sleep(0.01)
for attempt in range(100):
    state = service.get(work_id="atomicity-regression")
    try:
        result = service.checkpoint(
            work_id="atomicity-regression", actor_agent=agent,
            expected_revision=state["revision"],
            current_state={"writer": agent}, next_steps=["verify"],
            idempotency_key=agent,
        )
        print(result["revision"], flush=True)
        break
    except ValueError as exc:
        if "revision conflict" not in str(exc):
            raise
        time.sleep(0.01)
else:
    raise RuntimeError("revision retry budget exhausted")
"""
    workers = []
    try:
        for number in range(10):
            workers.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        child,
                        str(database),
                        str(start),
                        f"writer-{number}",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        start.touch()
        revisions = []
        for process in workers:
            stdout, stderr = process.communicate(timeout=45)
            assert process.returncode == 0, stderr
            revisions.append(int(stdout.strip()))
    finally:
        for process in workers:
            if process.poll() is None:
                process.kill()
                process.communicate()
    assert sorted(revisions) == list(range(2, 12))
    store = Store(database)
    assert WorkUnitService(store).get(work_id=WORK_ID)["revision"] == 11
    events = [
        event for event in store.list_trace(WORK_ID) if event["kind"] == "work_unit.checkpoint"
    ]
    assert len(events) == 10
    assert {event["attributes"]["revision"] for event in events} == set(range(2, 12))
    assert {event["attributes"]["actor_agent"] for event in events} == {
        f"writer-{number}" for number in range(10)
    }
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    verification = store.verify_work_unit(WORK_ID)
    assert verification["valid"]
    assert verification["entry_count"] == 11
