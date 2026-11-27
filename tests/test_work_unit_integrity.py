"""Offline integrity, rollback and externally anchored verification tests."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys

import pytest

from os29.store import Store
from os29.work_units import WorkUnitService

WORK_ID = "integrity-example"


def setup_unit(database):
    store = Store(database)
    service = WorkUnitService(store)
    service.create(
        work_id=WORK_ID,
        project="synthetic",
        objective="integrity",
        owner_agent="agent-a",
        allowed_scope=[],
        current_state={"phase": "initial"},
        known_good=[],
        known_bad=[],
        open_issues=[],
        next_steps=["verify"],
        context_refs=[],
    )
    return store, service


def receipt(service):
    return service.record_evidence_receipt(
        work_id=WORK_ID,
        actor_agent="agent-a",
        action="synthetic observation",
        outcome="observed",
        evidence={"message": "example"},
        next_action="verify",
    )


def test_chain_verifies_after_reopen_and_cli_uses_external_anchor(tmp_path):
    database = tmp_path / "chain.db"
    store, service = setup_unit(database)
    first = store.verify_work_unit(WORK_ID)
    assert first["valid"] and first["entry_count"] == 1
    receipt(service)
    service.checkpoint(
        work_id=WORK_ID,
        actor_agent="agent-a",
        expected_revision=1,
        current_state={"phase": "verified"},
        next_steps=["handoff"],
        idempotency_key="first",
    )
    service.handoff(
        work_id=WORK_ID,
        from_agent="agent-a",
        to_agent="agent-b",
        summary="ready",
        next_action="verify",
    )
    result = Store(database).verify_work_unit(WORK_ID)
    assert result["valid"] and result["entry_count"] == result["event_count"] == 4
    assert result["head_hash"] != first["head_hash"]
    check = subprocess.run(
        [
            sys.executable,
            "-m",
            "os29.cli",
            "--db",
            str(database),
            "verify",
            WORK_ID,
            "--expected-head",
            result["head_hash"],
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert check.returncode == 0, check.stderr
    assert json.loads(check.stdout)["external_anchor_checked"]
    wrong = subprocess.run(
        [
            sys.executable,
            "-m",
            "os29.cli",
            "--db",
            str(database),
            "verify",
            WORK_ID,
            "--expected-head",
            "f" * 64,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert wrong.returncode == 3
    assert "external_anchor_mismatch" in json.loads(wrong.stdout)["errors"]


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (
            "UPDATE trace_events SET event_json='{}' WHERE kind='work_unit.evidence_receipt'",
            "event_hash_mismatch:2",
        ),
        (
            "UPDATE trace_events SET action='changed' WHERE kind='work_unit.evidence_receipt'",
            "event_metadata_mismatch:2",
        ),
        (
            "UPDATE mission_capsules SET updated_at='changed'",
            "current_state_hash_mismatch",
        ),
        (
            "UPDATE work_unit_integrity SET previous_hash='changed' WHERE sequence=2",
            "broken_link:2",
        ),
        (
            "UPDATE work_unit_integrity SET state_hash='changed' WHERE sequence=1",
            "entry_hash_mismatch:1",
        ),
        (
            "DELETE FROM work_unit_integrity WHERE sequence=2",
            "missing_or_unsealed_events",
        ),
    ],
)
def test_tamper_detected(tmp_path, mutation, expected):
    database = tmp_path / "tamper.db"
    store, service = setup_unit(database)
    receipt(service)
    assert store.verify_work_unit(WORK_ID)["valid"]
    with sqlite3.connect(database) as connection:
        connection.execute(mutation)
    verification = store.verify_work_unit(WORK_ID)
    assert not verification["valid"]
    assert expected in verification["errors"]


def test_truncation_requires_external_anchor(tmp_path):
    database = tmp_path / "anchor.db"
    store, service = setup_unit(database)
    second = receipt(service)
    head = store.verify_work_unit(WORK_ID)["head_hash"]
    # Receipt does not change the capsule; deleting both rows truncates a
    # structurally valid chain. Only a previously retained head proves this.
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM work_unit_integrity WHERE sequence=2")
        connection.execute("DELETE FROM trace_events WHERE event_id=?", (second["event_id"],))
    assert store.verify_work_unit(WORK_ID)["valid"]
    assert not store.verify_work_unit(WORK_ID, expected_head=head)["valid"]


def test_chain_write_failure_rolls_back_state_and_event(tmp_path):
    database = tmp_path / "rollback.db"
    store, service = setup_unit(database)
    before = store.get_capsule(WORK_ID)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TRIGGER reject_chain BEFORE INSERT ON work_unit_integrity
            BEGIN SELECT RAISE(ABORT, 'injected integrity failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected integrity failure"):
        service.checkpoint(
            work_id=WORK_ID,
            actor_agent="agent-a",
            expected_revision=1,
            current_state={"phase": "must-not-commit"},
            next_steps=["verify"],
        )
    reopened = Store(database)
    assert reopened.get_capsule(WORK_ID) == before
    assert reopened.verify_work_unit(WORK_ID)["entry_count"] == 1
    assert reopened.verify_work_unit(WORK_ID)["valid"]


def test_legacy_history_is_not_silently_certified(tmp_path):
    database = tmp_path / "legacy.db"
    _store, service = setup_unit(database)
    receipt(service)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE work_unit_integrity")
    reopened = Store(database)
    assert "unsealed_history" in reopened.verify_work_unit(WORK_ID)["errors"]
    receipt(WorkUnitService(reopened))
    result = reopened.verify_work_unit(WORK_ID)
    assert not result["valid"]
    assert "missing_or_unsealed_events" in result["errors"]


def test_missing_unit_and_bad_external_head(tmp_path):
    store = Store(tmp_path / "empty.db")
    assert not store.verify_work_unit("missing")["valid"]
    with pytest.raises(ValueError, match="64-character"):
        store.verify_work_unit("missing", expected_head="invalid")
