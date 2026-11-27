"""Public MCP capability policy with real local effects on isolated fixtures."""

from __future__ import annotations

import json
import sqlite3
import sys

import pytest

from os29 import mcp_stdio
from os29.store import Store


@pytest.fixture
def context(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    database = tmp_path / "isolated.db"
    policy = tmp_path / "policy.json"
    monkeypatch.setattr(mcp_stdio, "DB_PATH", database)
    monkeypatch.delenv("OS29_MCP_POLICY_FILE", raising=False)

    def configure(**overrides):
        options = {"workspace_root": str(workspace), **overrides}
        policy.write_text(json.dumps(options), encoding="utf-8")
        monkeypatch.setenv("OS29_MCP_POLICY_FILE", str(policy))

    return workspace, database, configure


def invoke(name, args):
    response = mcp_stdio.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        }
    )
    result = response["result"]
    return result["isError"], json.loads(result["content"][0]["text"])


def test_default_denies_free_form_command_and_persists_safe_audit(context):
    workspace, database, _ = context
    error, payload = invoke("os29_terminal_exec", {"command": "unknown; arbitrary"})
    assert error and payload["error"] == "command_alias_not_approved"
    events = Store(database).recent_events()
    assert events[0]["kind"] == "mcp.policy.decision"
    assert events[0]["outcome"] == "blocked"
    assert "unknown; arbitrary" not in json.dumps(events)
    assert not list(workspace.iterdir())


def test_workspace_paths_literal_search_and_file_bounds(context):
    workspace, database, configure = context
    configure(max_file_bytes=128)
    outside = workspace.parent / "outside.txt"
    outside.write_text("outside-marker", encoding="utf-8")
    for path in ("../outside.txt", str(outside)):
        error, payload = invoke("os29_file_read", {"path": path})
        assert error and payload["error"] == "path_outside_workspace"
    error, _ = invoke("os29_file_write", {"path": "../outside.txt", "content": "changed"})
    assert error and outside.read_text() == "outside-marker"
    error, result = invoke(
        "os29_file_write", {"path": "inside.txt", "content": "literal [x]\nnext"}
    )
    assert not error and result["success"]
    error, result = invoke("os29_file_read", {"path": "inside.txt", "start_line": 1, "end_line": 1})
    assert not error and result["content"] == "literal [x]"
    error, result = invoke("os29_code_search", {"pattern": "[x]"})
    assert not error and result["match_count"] == 1
    (workspace / "large.txt").write_text("a" * 129, encoding="utf-8")
    error, result = invoke("os29_file_read", {"path": "large.txt"})
    assert error and result["error"] == "file_size_limit"
    assert Store(database).stats()


def test_symlink_escape_is_denied(context):
    workspace, _, configure = context
    configure()
    outside = workspace.parent / "external.txt"
    outside.write_text("external", encoding="utf-8")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    error, payload = invoke("os29_file_read", {"path": "link.txt"})
    assert error and payload["error"] == "path_outside_workspace"


def test_read_only_does_not_mutate_database_or_workspace(context):
    workspace, database, configure = context
    Store(database)
    before = Store(database).stats()
    configure(mode="read-only")
    error, payload = invoke("os29_status", {})
    assert not error and payload == before
    error, payload = invoke("os29_file_write", {"path": "new.txt", "content": "data"})
    assert error and payload["error"] == "read_only_policy"
    assert not (workspace / "new.txt").exists()
    assert Store(database).stats() == before
    with pytest.raises(sqlite3.OperationalError):
        Store(database, read_only=True).save_capsule(
            "new",
            {
                "project": "test",
                "objective": "test",
                "current_state": {},
                "known_good": [],
                "known_bad": [],
                "open_issues": [],
                "next_steps": [],
            },
        )


def test_dry_run_and_explicit_allow_deny_lists(context):
    workspace, database, configure = context
    configure(
        mode="dry-run",
        allow_tools=["os29_file_write", "os29_status"],
        deny_tools=["os29_status"],
    )
    error, payload = invoke("os29_file_write", {"path": "planned.txt", "content": "data"})
    assert not error and payload["executed"] is False
    assert not (workspace / "planned.txt").exists()
    assert not database.exists()
    error, payload = invoke("os29_status", {})
    assert error and payload["error"] == "tool_not_allowed"
    assert not database.exists()


def test_command_alias_executes_exact_argv_and_bounds_time_output(context):
    _workspace, _, configure = context
    configure(
        commands={
            "smoke": [sys.executable, "-c", "print('POLICY_SMOKE_PASS')"],
            "slow": [sys.executable, "-c", "import time; time.sleep(3)"],
            "flood": [sys.executable, "-c", "print('x' * 20000)"],
        },
        max_timeout_seconds=1,
        max_output_bytes=1024,
    )
    error, result = invoke("os29_terminal_exec", {"command": "smoke"})
    assert not error and result["exit_code"] == 0
    assert result["stdout"].strip() == "POLICY_SMOKE_PASS"
    error, result = invoke("os29_terminal_exec", {"command": "smoke; other"})
    assert error and result["error"] == "command_alias_not_approved"
    error, result = invoke("os29_terminal_exec", {"command": "smoke", "timeout_seconds": 2})
    assert error and result["error"] == "command_timeout_limit"
    _, result = invoke("os29_terminal_exec", {"command": "slow"})
    assert result["exit_code"] == -1 and result["reason"] == "command_timeout"
    _, result = invoke("os29_terminal_exec", {"command": "flood"})
    assert result["exit_code"] == -1 and result["reason"] == "command_output_limit"
    assert len((result["stdout"] + result["stderr"]).encode("utf-8")) <= 1024
