from __future__ import annotations

from os29 import mcp_stdio
from os29.store import Store
from os29.work_units import WorkUnitService


def _create(service: WorkUnitService) -> dict:
    return service.create(
        work_id="wu-pytest-handoff-001",
        project="OS28/OS29",
        objective="Verify a second agent can resume from only a Work Unit ID.",
        owner_agent="agent-a",
        allowed_scope=["C:/lab"],
        current_state={"phase": "implementation", "artifact": "work_units.py"},
        known_good=["OS29 mission_capsules is canonical."],
        known_bad=[],
        open_issues=[],
        next_steps=["Agent B should resume this Work Unit by ID."],
        context_refs=["trace:wu-pytest-handoff-001"],
    )


def test_work_unit_resume_uses_only_id_and_survives_store_reopen(tmp_path):
    database = tmp_path / "os29.db"
    created = _create(WorkUnitService(Store(database)))

    resumed = WorkUnitService(Store(database)).resume(
        work_id=created["work_id"],
        agent_id="agent-b",
    )

    assert resumed["work_id"] == "wu-pytest-handoff-001"
    assert (
        resumed["objective"]
        == "Verify a second agent can resume from only a Work Unit ID."
    )
    assert resumed["owner_agent"] == "agent-a"
    assert resumed["next_action"] == "Agent B should resume this Work Unit by ID."
    assert resumed["context_refs"] == ["trace:wu-pytest-handoff-001"]


def test_handoff_and_evidence_receipt_are_persisted_in_the_same_os29_trace(tmp_path):
    store = Store(tmp_path / "os29.db")
    service = WorkUnitService(store)
    _create(service)

    receipt = service.record_evidence_receipt(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-a",
        action="implemented contract",
        outcome="success",
        evidence={"test": "red then green"},
        next_action="handoff to agent-b",
    )
    handoff = service.handoff(
        work_id="wu-pytest-handoff-001",
        from_agent="agent-a",
        to_agent="agent-b",
        summary="Contract and evidence are persisted.",
        next_action="Resume by ID and verify the receipt.",
    )

    events = Store(tmp_path / "os29.db").list_trace("wu-pytest-handoff-001")
    assert receipt["event_id"] in {event["event_id"] for event in events}
    assert handoff["status"] == "handoff_ready"
    assert [event["kind"] for event in events] == [
        "work_unit.created",
        "work_unit.evidence_receipt",
        "work_unit.handoff",
    ]


def test_work_unit_list_is_backed_by_existing_mission_capsules_only(tmp_path):
    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)

    listed = service.list(limit=10)

    assert listed["count"] == 1
    assert listed["work_units"][0]["work_id"] == "wu-pytest-handoff-001"
    assert listed["work_units"][0]["status"] == "active"


def test_mcp_work_unit_tools_create_handoff_and_resume_by_id(tmp_path):
    store = Store(tmp_path / "os29.db")
    tools = {tool["name"] for tool in mcp_stdio.schemas()}
    assert {
        "os29_work_unit_create",
        "os29_work_unit_handoff",
        "os29_work_unit_resume",
        "os29_evidence_receipt_record",
    } <= tools

    created = mcp_stdio._dispatch(
        store,
        "os29_work_unit_create",
        {
            "work_id": "wu-mcp-001",
            "project": "OS28/OS29",
            "objective": "MCP resume contract",
            "owner_agent": "agent-a",
            "allowed_scope": ["C:/lab"],
            "current_state": {"phase": "test"},
            "known_good": ["store"],
            "known_bad": [],
            "open_issues": [],
            "next_steps": ["resume"],
            "context_refs": ["trace:wu-mcp-001"],
        },
        "trace-test",
    )
    assert created["work_id"] == "wu-mcp-001"

    mcp_stdio._dispatch(
        store,
        "os29_evidence_receipt_record",
        {
            "work_id": "wu-mcp-001",
            "actor_agent": "agent-a",
            "action": "MCP create verified",
            "outcome": "success",
            "evidence": {"assertion": "create returned work_id"},
            "next_action": "handoff",
        },
        "trace-test",
    )
    mcp_stdio._dispatch(
        store,
        "os29_work_unit_handoff",
        {
            "work_id": "wu-mcp-001",
            "from_agent": "agent-a",
            "to_agent": "agent-b",
            "summary": "ready for another agent",
            "next_action": "resume by work ID",
        },
        "trace-test",
    )
    resumed = mcp_stdio._dispatch(
        store,
        "os29_work_unit_resume",
        {
            "work_id": "wu-mcp-001",
            "agent_id": "agent-b",
        },
        "trace-test",
    )
    assert resumed["resumed_by"] == "agent-b"
    assert resumed["owner_agent"] == "agent-b"
    assert resumed["evidence_receipt_count"] == 1


def test_checkpoint_revision_idempotency_and_reopen(tmp_path):
    import pytest

    database = tmp_path / "os29.db"
    service = WorkUnitService(Store(database))
    _create(service)
    first = service.checkpoint(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-a",
        expected_revision=1,
        current_state={"phase": "smoke-tested"},
        next_steps=["Agent B should inspect the recorded artifact"],
        files_touched=["C:/lab/example.py"],
        tools_used=["python"],
        tests=[{"command": "python example.py", "exit_code": 0}],
        artifacts=["C:/lab/output.txt"],
        idempotency_key="checkpoint-0001",
    )
    assert first["revision"] == 2
    replay = service.checkpoint(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-a",
        expected_revision=1,
        current_state={"phase": "smoke-tested"},
        next_steps=["Agent B should inspect the recorded artifact"],
        idempotency_key="checkpoint-0001",
    )
    assert replay["idempotent_replay"] is True
    assert replay["event_id"] == first["event_id"]
    with pytest.raises(ValueError, match="revision conflict"):
        WorkUnitService(Store(database)).checkpoint(
            work_id="wu-pytest-handoff-001",
            actor_agent="agent-b",
            expected_revision=1,
            current_state={"phase": "overwritten"},
            next_steps=["bad"],
        )
    reopened = WorkUnitService(Store(database)).get(work_id="wu-pytest-handoff-001")
    assert reopened["revision"] == 2
    assert reopened["current_state"]["phase"] == "smoke-tested"
    assert reopened["files_touched"] == ["C:/lab/example.py"]
    assert reopened["tests"][0]["exit_code"] == 0


def test_completion_requires_persisted_executable_evidence(tmp_path):
    import pytest

    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)
    with pytest.raises(ValueError, match="evidence receipt"):
        service.complete(
            work_id="wu-pytest-handoff-001", actor_agent="agent-b", expected_revision=1
        )
    service.record_evidence_receipt(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-b",
        action="claim success",
        outcome="success",
        evidence={"test": "PASS"},
        next_action="complete",
    )
    with pytest.raises(ValueError, match="evidence receipt"):
        service.complete(
            work_id="wu-pytest-handoff-001", actor_agent="agent-b", expected_revision=1
        )
    service.record_evidence_receipt(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-b",
        action="real Python smoke",
        outcome="success",
        evidence={
            "command": "python -c 'print(42)'",
            "exit_code": 0,
            "stdout": "42\n",
            "stderr": "",
        },
        next_action="complete",
    )
    done = service.complete(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-b",
        expected_revision=1,
    )
    assert done["status"] == "completed"
    assert done["revision"] == 2
    assert service.complete(
        work_id="wu-pytest-handoff-001", actor_agent="agent-b", expected_revision=2
    )["idempotent_replay"]
    with pytest.raises(ValueError, match="completed"):
        service.checkpoint(
            work_id="wu-pytest-handoff-001",
            actor_agent="agent-b",
            expected_revision=2,
            current_state={"test": True},
            next_steps=["no"],
        )


def test_receipts_export_to_canonical_db_artifacts_folder(tmp_path):
    import json

    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)
    service.record_evidence_receipt(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-a",
        action="test run",
        outcome="success",
        evidence={
            "command": "python --version",
            "exit_code": 0,
            "stdout": "Python 3.12.0",
            "stderr": "",
        },
        next_action="handoff",
    )
    result = service.export_receipt(work_id="wu-pytest-handoff-001")
    assert result["json_path"].startswith(str(tmp_path))
    assert result["markdown_path"].startswith(str(tmp_path))
    parsed = json.loads(open(result["json_path"], encoding="utf-8").read())
    assert parsed["evidence"][0]["details"]["exit_code"] == 0
    markdown = open(result["markdown_path"], encoding="utf-8").read()
    assert "Evidence Receipt" in markdown
    assert "Python 3.12.0" in markdown


def test_mcp_schema_dispatch_checkpoint_complete_and_receipt(tmp_path):
    store = Store(tmp_path / "os29.db")
    names = {tool["name"] for tool in mcp_stdio.schemas()}
    assert {
        "os29_work_unit_checkpoint",
        "os29_work_unit_complete",
        "os29_work_unit_fail",
        "os29_work_unit_receipt",
        "os29_work_unit_receipt_export",
    } <= names
    _create(WorkUnitService(store))
    checkpoint = mcp_stdio._dispatch(
        store,
        "os29_work_unit_checkpoint",
        {
            "work_id": "wu-pytest-handoff-001",
            "actor_agent": "agent-a",
            "expected_revision": 1,
            "current_state": {"phase": "handoff"},
            "next_steps": ["agent-b verify"],
        },
        "trace-mcp",
    )
    assert checkpoint["revision"] == 2
    mcp_stdio._dispatch(
        store,
        "os29_evidence_receipt_record",
        {
            "work_id": "wu-pytest-handoff-001",
            "actor_agent": "agent-b",
            "action": "smoke test",
            "outcome": "success",
            "evidence": {
                "command": "python --version",
                "exit_code": 0,
                "stdout": "Python 3.12.0",
            },
            "next_action": "complete",
        },
        "trace-mcp",
    )
    assert (
        mcp_stdio._dispatch(
            store,
            "os29_work_unit_complete",
            {
                "work_id": "wu-pytest-handoff-001",
                "actor_agent": "agent-b",
                "expected_revision": 2,
            },
            "trace-mcp",
        )["status"]
        == "completed"
    )
    assert (
        mcp_stdio._dispatch(
            store,
            "os29_work_unit_receipt",
            {
                "work_id": "wu-pytest-handoff-001",
            },
            "trace-mcp",
        )["receipt"]["status"]
        == "completed"
    )


def test_two_clients_cannot_overwrite_same_revision(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    db_path = tmp_path / "os29.db"
    _create(WorkUnitService(Store(db_path)))

    def independently_checkpoint(name):
        service = WorkUnitService(Store(db_path))
        try:
            return service.checkpoint(
                work_id="wu-pytest-handoff-001",
                actor_agent=name,
                expected_revision=1,
                current_state={"writer": name},
                next_steps=["review"],
            )["revision"]
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(independently_checkpoint, ["client-a", "client-b"]))
    assert outcomes.count(2) == 1
    assert (
        len([outcome for outcome in outcomes if "revision conflict" in str(outcome)])
        == 1
    )
    assert (
        WorkUnitService(Store(db_path)).get(work_id="wu-pytest-handoff-001")["revision"]
        == 2
    )


def test_atomic_create_does_not_overwrite_original_work_unit(tmp_path):
    import pytest

    database = tmp_path / "os29.db"
    _create(WorkUnitService(Store(database)))
    with pytest.raises(ValueError, match="already exists"):
        _create(WorkUnitService(Store(database)))
    assert (
        WorkUnitService(Store(database)).get(work_id="wu-pytest-handoff-001")[
            "revision"
        ]
        == 1
    )


def test_handoff_sender_matches_owner_and_duplicate_is_idempotent(tmp_path):
    import pytest

    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)
    with pytest.raises(ValueError, match="sender"):
        service.handoff(
            work_id="wu-pytest-handoff-001",
            from_agent="wrong-agent",
            to_agent="agent-b",
            summary="bad handoff",
            next_action="verify",
        )
    first = service.handoff(
        work_id="wu-pytest-handoff-001",
        from_agent="agent-a",
        to_agent="agent-b",
        summary="handoff",
        next_action="verify",
    )
    again = service.handoff(
        work_id="wu-pytest-handoff-001",
        from_agent="agent-a",
        to_agent="agent-b",
        summary="handoff",
        next_action="verify",
    )
    assert again["idempotent_replay"] is True
    assert service.get(work_id="wu-pytest-handoff-001")["revision"] == 2
    assert first["status"] == again["status"]


def test_evidence_receipt_idempotency_and_conflicts(tmp_path):
    import pytest

    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)
    kwargs = dict(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-a",
        action="run test",
        outcome="success",
        evidence={"command": "python -V", "exit_code": 0, "stdout": "Python 3.12"},
        next_action="verify",
        idempotency_key="receipt-dedup-001",
    )
    first = service.record_evidence_receipt(**kwargs)
    second = service.record_evidence_receipt(**kwargs)
    assert second["event_id"] == first["event_id"]
    assert second["idempotent_replay"] is True
    with pytest.raises(ValueError, match="idempotency key conflicts"):
        service.record_evidence_receipt(**{**kwargs, "outcome": "failure"})
    assert (
        service.resume(work_id="wu-pytest-handoff-001", agent_id="agent-b")[
            "evidence_receipt_count"
        ]
        == 1
    )


def test_resume_context_pack_is_compact_and_has_next_action(tmp_path):
    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)
    resumed = service.resume(work_id="wu-pytest-handoff-001", agent_id="agent-b")
    assert "Verify a second agent" in resumed["context_pack"]
    assert "Agent B should resume" in resumed["context_pack"]
    assert resumed["context_pack_words"] < 300


def test_markdown_receipt_renders_nested_smoke_and_pytest_evidence(tmp_path):
    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)
    service.record_evidence_receipt(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-b",
        action="finish validation",
        outcome="success",
        evidence={
            "smoke": {
                "command": "python validator.py --input fixture.json",
                "exit_code": 0,
                "stdout": "valid",
                "stderr": "",
            },
            "pytest": {
                "command": "python -m pytest tests -q",
                "exit_code": 0,
                "stdout": "16 passed",
                "stderr": "",
            },
        },
        next_action="complete",
    )
    receipt = service.receipt(work_id="wu-pytest-handoff-001")
    markdown = receipt["markdown"]
    assert "smoke: command=" in markdown
    assert "pytest: command=" in markdown
    assert "16 passed" in markdown
    assert "exit_code=0" in markdown
    assert "not verified" not in markdown


def test_completion_requires_receipt_from_completing_agent_and_accepts_nested_tests(
    tmp_path,
):
    import pytest

    service = WorkUnitService(Store(tmp_path / "os29.db"))
    _create(service)
    service.record_evidence_receipt(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-a",
        action="agent a smoke",
        outcome="success",
        evidence={
            "command": "python --version",
            "exit_code": 0,
            "stdout": "Python 3.12",
        },
        next_action="agent b implementation",
    )
    with pytest.raises(ValueError, match="completing agent"):
        service.complete(
            work_id="wu-pytest-handoff-001",
            actor_agent="agent-b",
            expected_revision=1,
        )
    service.record_evidence_receipt(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-b",
        action="gpt2 nested smoke and pytest",
        outcome="success",
        evidence={
            "smoke": {
                "command": "python validator.py --input fixture.json",
                "exit_code": 0,
                "stdout": "valid",
                "stderr": "",
            },
            "pytest": {
                "command": "python -m pytest tests -q",
                "exit_code": 0,
                "stdout": "16 passed",
                "stderr": "",
            },
        },
        next_action="complete",
    )
    completed = service.complete(
        work_id="wu-pytest-handoff-001",
        actor_agent="agent-b",
        expected_revision=1,
    )
    assert completed["status"] == "completed"
    done_events = [
        event
        for event in service.store.list_trace("wu-pytest-handoff-001")
        if event["kind"] == "work_unit.completed"
    ]
    assert len(done_events) == 1
    assert len(done_events[0]["attributes"]["verification_event_ids"]) == 1
