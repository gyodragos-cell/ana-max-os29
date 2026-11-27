"""Comprehensive MCP STDIO protocol & dispatch coverage tests."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from os29 import mcp_stdio
from os29.mcp_validation import MAX_FRAME_BYTES
from os29.models import TraceEvent
from os29.store import Store


def _call(name: str, arguments: dict[str, object], req_id: int = 1) -> dict[str, object]:
    resp = mcp_stdio.handle(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert resp is not None
    return resp


def _decoded(resp: dict[str, object]) -> dict[str, object]:
    result = resp["result"]
    assert isinstance(result, dict)
    text = result["content"][0]["text"]
    return json.loads(text)


def test_mcp_all_core_and_tower_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "mcp.db"
    scope = tmp_path / "scope.json"
    scope.write_text(
        json.dumps(
            {
                "schema_version": "os29.scope.v1",
                "approved_hosts": ["127.0.0.1"],
                "approved_ports": [8766],
            }
        ),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "mode": "normal",
                "workspace_root": str(tmp_path),
                "commands": {"pyver": [sys.executable, "-c", "print('ok')"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_stdio, "DB_PATH", db)
    monkeypatch.setattr(mcp_stdio, "SCOPE_PATH", scope)
    monkeypatch.setenv("OS29_MCP_POLICY_FILE", str(policy))

    init = mcp_stdio.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init is not None and "protocolVersion" in init["result"]
    listed = mcp_stdio.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert listed is not None and len(listed["result"]["tools"]) == len(mcp_stdio.schemas())

    assert _decoded(_call("os29_status", {}))["status"] == "ok"
    assert (
        _decoded(_call("os29_scope_check", {"target": "http://127.0.0.1:8766/health"}))["allowed"]
        is True
    )

    with patch("os29.mcp_stdio.snapshot_loopback", return_value={"status": "complete"}):
        assert _decoded(_call("os29_runtime_snapshot", {}))["status"] == "complete"

    evt = TraceEvent(
        trace_id="t-mcp",
        source="mcp",
        component="test",
        kind="diagnostic",
        action="fail_probe",
        outcome="failure",
    ).to_dict()
    rec = _decoded(_call("os29_trace_record", {"event": evt}))
    assert "event_id" in rec
    assert _decoded(_call("os29_trace_get", {"trace_id": "t-mcp"}))["event_count"] == 1
    assert _decoded(_call("os29_trace_diagnose", {"trace_id": "t-mcp"}))["trace_id"] == "t-mcp"

    _decoded(
        _call(
            "os29_mission_capsule_save",
            {
                "mission_id": "m-mcp",
                "capsule": {
                    "project": "mcp",
                    "objective": "obj",
                    "current_state": {"step": 1},
                    "known_good": [],
                    "known_bad": [],
                    "open_issues": [],
                    "next_steps": [],
                },
            },
        )
    )
    assert (
        _decoded(_call("os29_mission_capsule_get", {"mission_id": "m-mcp"}))["mission_id"]
        == "m-mcp"
    )
    assert _call("os29_mission_capsule_get", {"mission_id": "none"})["result"]["isError"] is True

    _decoded(
        _call(
            "os29_work_unit_create",
            {
                "work_id": "wu-mcp-1",
                "project": "mcp",
                "objective": "test",
                "owner_agent": "a",
                "allowed_scope": [],
                "current_state": {"p": 1},
                "known_good": [],
                "known_bad": [],
                "open_issues": [],
                "next_steps": [],
                "context_refs": [],
            },
        )
    )
    assert _decoded(_call("os29_work_unit_get", {"work_id": "wu-mcp-1"}))["work_id"] == "wu-mcp-1"
    assert len(_decoded(_call("os29_work_unit_list", {"limit": 10}))["work_units"]) == 1
    _decoded(
        _call(
            "os29_evidence_receipt_record",
            {
                "work_id": "wu-mcp-1",
                "actor_agent": "a",
                "action": "check",
                "outcome": "success",
                "evidence": {"k": "v"},
                "next_action": "checkpoint",
            },
        )
    )
    _decoded(
        _call(
            "os29_work_unit_checkpoint",
            {
                "work_id": "wu-mcp-1",
                "actor_agent": "a",
                "expected_revision": 1,
                "current_state": {"p": 2},
                "next_steps": ["handoff"],
            },
        )
    )
    _decoded(
        _call(
            "os29_work_unit_handoff",
            {
                "work_id": "wu-mcp-1",
                "from_agent": "a",
                "to_agent": "b",
                "summary": "handing off",
                "next_action": "complete",
            },
        )
    )
    assert (
        _decoded(_call("os29_work_unit_resume", {"work_id": "wu-mcp-1", "agent_id": "b"}))[
            "work_id"
        ]
        == "wu-mcp-1"
    )
    _decoded(
        _call(
            "os29_evidence_receipt_record",
            {
                "work_id": "wu-mcp-1",
                "actor_agent": "b",
                "action": "smoke_verify",
                "outcome": "success",
                "evidence": {"command": "pytest -q", "exit_code": 0, "stdout": "ok"},
                "next_action": "complete",
            },
        )
    )
    assert (
        _decoded(_call("os29_work_unit_receipt", {"work_id": "wu-mcp-1"}))["receipt"]["work_id"]
        == "wu-mcp-1"
    )
    comp = _decoded(
        _call(
            "os29_work_unit_complete",
            {"work_id": "wu-mcp-1", "actor_agent": "b", "expected_revision": 3},
        )
    )
    assert comp["status"] == "completed"
    assert _decoded(_call("os29_work_unit_verify", {"work_id": "wu-mcp-1"}))["valid"] is True

    _decoded(
        _call(
            "os29_work_unit_create",
            {
                "work_id": "wu-mcp-fail",
                "project": "mcp",
                "objective": "fail",
                "owner_agent": "a",
                "allowed_scope": [],
                "current_state": {"p": 1},
                "known_good": [],
                "known_bad": [],
                "open_issues": [],
                "next_steps": [],
                "context_refs": [],
            },
        )
    )
    fail_res = _decoded(
        _call(
            "os29_work_unit_fail",
            {
                "work_id": "wu-mcp-fail",
                "actor_agent": "a",
                "expected_revision": 1,
                "reason": "blocked",
            },
        )
    )
    assert fail_res["status"] == "blocked"

    cand = _decoded(
        _call(
            "os29_experience_candidate_add",
            {
                "problem_key": "prob",
                "cause": "cause",
                "solution": "sol",
                "outcome": "partial",
                "source_event_ids": [rec["event_id"]],
            },
        )
    )
    _decoded(
        _call(
            "os29_experience_validate",
            {
                "lesson_id": cand["lesson_id"],
                "verification_event_id": rec["event_id"],
                "verified_by": "qa",
            },
        )
    )
    assert (
        len(
            _decoded(
                _call("os29_experience_search", {"query": "prob", "include_candidates": True})
            )["experiences"]
        )
        >= 1
    )

    _decoded(
        _call(
            "os29_session_save", {"session_id": "sm-1", "payload": {"title": "T", "summary": "S"}}
        )
    )
    assert _decoded(_call("os29_session_get", {"session_id": "sm-1"}))["session_id"] == "sm-1"
    assert _call("os29_session_get", {"session_id": "nope"})["result"]["isError"] is True
    assert len(_decoded(_call("os29_session_list", {"limit": 5}))["sessions"]) == 1

    assert _decoded(_call("os29_capabilities_list", {"limit": 5}))["capabilities"] == []
    assert _decoded(_call("os29_capability_edges_list", {"limit": 5}))["edges"] == []
    report = _decoded(_call("os29_intelligence_report", {"event_limit": 20}))
    assert report["schema_version"] == "os29.intelligence_report.v1"
    assert report["evidence_window"]["max_events_examined"] == 20
    assert report["self_building_guard"]["automatic_code_changes"] is False
    _decoded(_call("os29_memory_search", {"query": "mcp"}))

    with patch(
        "os29.mcp_stdio.answer_from_memory",
        return_value={"answer_status": "grounded", "answer": "ok"},
    ):
        assert _decoded(_call("os29_memory_answer", {"query": "q"}))["answer_status"] == "grounded"
    assert _call("os29_memory_answer", {"query": "q", "bad_arg": 1})["result"]["isError"] is True

    _decoded(_call("os29_file_write", {"path": "hello.txt", "content": "alpha\nbeta\n"}))
    assert (
        _decoded(_call("os29_file_read", {"path": "hello.txt", "start_line": 2, "end_line": 2}))[
            "content"
        ]
        == "beta"
    )
    assert _decoded(_call("os29_code_search", {"pattern": "beta"}))["match_count"] >= 1
    assert _decoded(_call("os29_terminal_exec", {"command": "pyver"}))["exit_code"] == 0
    assert _call("os29_terminal_exec", {"command": "blocked_alias"})["result"]["isError"] is True

    with patch("os29.mcp_stdio._probe_port", return_value="offline"):
        boot = _decoded(_call("tower_bootstrap", {"agent_id": "agent-a"}))
        assert boot["agent_id"] == "agent-a"
        assert any(row["id"] == "sm-1" for row in boot["recent_sessions"])
        assert _decoded(_call("tower_resume", {"mission_id": "m-mcp"}))["mission_id"] == "m-mcp"
        assert "not found" in str(
            _decoded(_call("tower_resume", {"mission_id": "missing"}))["error"]
        )
        _decoded(
            _call(
                "tower_checkpoint",
                {
                    "mission_id": "m-tower",
                    "payload": {
                        "project": "t",
                        "objective": "o",
                        "current_state": {},
                        "known_good": [],
                        "known_bad": [],
                        "open_issues": [],
                        "next_steps": [],
                    },
                },
            )
        )
        assert (
            _call("tower_checkpoint", {"mission_id": "m-tower", "payload": "bad"})["result"][
                "isError"
            ]
            is True
        )
        search = _decoded(_call("tower_memory_search", {"query": "mcp", "scope": "session"}))
        assert search["scope"] == "session"
        assert isinstance(search["results"], list)

    # Ensure receipt_export also works in normal store
    Store(db)
    assert "markdown_path" in _decoded(
        _call("os29_work_unit_receipt_export", {"work_id": "wu-mcp-1"})
    )


def test_mcp_stdio_main_loop_and_encode_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    huge = {"jsonrpc": "2.0", "id": 1, "result": {"data": "x" * (mcp_stdio.MAX_OUTPUT_BYTES + 10)}}
    encoded = json.loads(mcp_stdio.encode_response(huge))
    assert encoded["error"]["code"] == -32000

    valid_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode("utf-8") + b"\n"
    bad_json = b"{broken\n"
    oversized = b"x" * (MAX_FRAME_BYTES + 2) + b"\n"
    fake_in = io.BytesIO(valid_req + bad_json + oversized)
    fake_buf = io.BytesIO()

    class FakeStdout:
        def __init__(self, buf: io.BytesIO) -> None:
            self.buffer = buf

        def write(self, data: str) -> int:
            return self.buffer.write(data.encode("utf-8"))

        def flush(self) -> None:
            return None

    monkeypatch.setattr(mcp_stdio, "DB_PATH", tmp_path / "loop.db")
    monkeypatch.setattr(sys, "stdin", type("FakeStdin", (), {"buffer": fake_in})())
    monkeypatch.setattr(sys, "stdout", FakeStdout(fake_buf))
    with patch("os29.mcp_stdio.log_startup"), patch("os29.mcp_stdio.log_shutdown"):
        mcp_stdio.main()

    lines = [
        json.loads(line)
        for line in fake_buf.getvalue().decode("utf-8").splitlines()
        if line.strip()
    ]
    assert lines[0] == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert lines[1]["error"]["code"] == -32700
    assert lines[2]["error"]["code"] == -32600
