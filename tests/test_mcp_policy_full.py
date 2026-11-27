# FILE: tests/test_mcp_policy_full.py
import json
import sys

import pytest

from os29.mcp_policy import (
    CapabilityPolicy,
    PolicyDenied,
    bounded_command,
    bounded_file_read,
    bounded_literal_search,
)
from os29.mcp_stdio import call_tool
from os29.redaction import REDACTED, redact_value


@pytest.fixture
def configure(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    monkeypatch.setenv("OS29_MCP_POLICY_FILE", str(path))

    def load(**config):
        path.write_text(json.dumps(config), encoding="utf-8")
        return CapabilityPolicy.from_environment()

    return load


def test_default_and_unknown_tool(monkeypatch):
    monkeypatch.delenv("OS29_MCP_POLICY_FILE", raising=False)
    assert CapabilityPolicy.from_environment().prepare("os29_status", {}) == {}
    with pytest.raises(ValueError, match="unknown OS29 tool") as error:
        call_tool("unknown_tool", {})
    assert "unknown_tool" in str(error.value)


def test_allow_and_deny(configure):
    policy = configure(allow_tools=["os29_status", "os29_trace_get"], deny_tools=["os29_trace_get"])
    assert policy.prepare("os29_status", {}) == {}
    for name in ("os29_trace_get", "os29_file_write"):
        with pytest.raises(PolicyDenied, match="tool_not_allowed") as error:
            policy.prepare(name, {})
        assert str(error.value) == "tool_not_allowed"


def test_read_only(configure):
    policy = configure(mode="read-only")
    assert policy.prepare("os29_status", {}) == {}
    for name in ("os29_file_write", "os29_file_delete", "os29_terminal_exec"):
        with pytest.raises(PolicyDenied, match="read_only_policy") as error:
            policy.prepare(name, {})
        assert str(error.value) == "read_only_policy"


def test_dry_run(configure, tmp_path, monkeypatch):
    from os29 import mcp_stdio

    database = tmp_path / "unused.db"
    monkeypatch.setattr(mcp_stdio, "DB_PATH", database)
    configure(mode="dry-run", workspace_root=str(tmp_path))
    result = call_tool("os29_file_write", {"path": "new.txt", "content": "test"})
    assert result == {
        "mode": "dry-run",
        "tool": "os29_file_write",
        "executed": False,
        "policy_allowed": True,
    }
    assert not (tmp_path / "new.txt").exists()
    assert not database.exists()


def test_redaction():
    source = {key: f"value-{key}" for key in ("password", "token", "api_key", "secret")}
    clean, count = redact_value({"nested": [source], "safe": "keep"})
    assert count == 4 and clean["safe"] == "keep"
    assert clean["nested"][0] == dict.fromkeys(source, REDACTED)
    assert REDACTED == "[REDACTED]"


def test_config_and_timeout(configure, tmp_path):
    policy = configure(
        workspace_root=str(tmp_path),
        max_timeout_seconds=3,
        commands={"smoke": [sys.executable, "-c", "print(1)"]},
        max_file_bytes=64,
        max_output_bytes=1024,
    )
    assert policy.workspace_root == tmp_path.resolve()
    assert policy.max_file_bytes == 64 and policy.max_output_bytes == 1024
    assert policy.commands["smoke"][0] == sys.executable
    assert policy.prepare("os29_terminal_exec", {"command": "smoke"})["timeout_seconds"] == 3
    assert policy.prepare("os29_memory_answer", {})["timeout_seconds"] == 3
    for name, args, reason in (
        ("os29_terminal_exec", {"command": "smoke", "timeout_seconds": 4}, "command_timeout_limit"),
        ("os29_terminal_exec", {"command": "other"}, "command_alias_not_approved"),
        ("os29_memory_answer", {"timeout_seconds": 4}, "model_timeout_limit"),
    ):
        with pytest.raises(PolicyDenied, match=reason) as error:
            policy.prepare(name, args)
        assert str(error.value) == reason


@pytest.mark.parametrize(
    "config",
    [
        {"unknown": True},
        {"mode": "wrong"},
        {"workspace_root": "relative"},
        {"workspace_root": 1},
        {"commands": []},
        {"commands": {"": ["x"]}},
        {"commands": {"x": []}},
        {"commands": {"x": [1]}},
        {"commands": {"x": ["relative"]}},
        {"allow_tools": "x"},
        {"deny_tools": [""]},
        {"max_timeout_seconds": True},
        {"max_timeout_seconds": 91},
        {"max_file_bytes": 0},
        {"max_output_bytes": 1},
    ],
)
def test_invalid_config(configure, config):
    with pytest.raises(ValueError) as error:
        configure(**config)
    assert str(error.value)


def test_oversized_policy(tmp_path, monkeypatch):
    path = tmp_path / "huge.json"
    path.write_bytes(b" " * 65537)
    monkeypatch.setenv("OS29_MCP_POLICY_FILE", str(path))
    with pytest.raises(ValueError, match="size limit") as error:
        CapabilityPolicy.from_environment()
    assert str(error.value)


def test_paths_and_file_limits(configure, tmp_path):
    policy = configure(workspace_root=str(tmp_path), max_file_bytes=4)
    target = tmp_path / "x.txt"
    target.write_bytes(b"a\nb\n")
    assert policy.prepare("os29_file_read", {"path": "x.txt"})["path"] == str(target.resolve())
    assert bounded_file_read(str(target), 4, 2, 2)["content"] == "b"
    assert policy.prepare("os29_file_write", {"path": "x.txt", "content": "éé"})["content"] == "éé"
    for name, args, reason in (
        ("os29_file_write", {"path": "x.txt", "content": "ééé"}, "file_size_limit"),
        ("os29_file_read", {"path": "missing"}, "file_not_found"),
        ("os29_file_read", {"path": "../outside"}, "path_outside_workspace"),
        ("os29_code_search", {"pattern": ""}, "search_pattern_limit"),
        ("os29_code_search", {"pattern": "x", "max_results": 101}, "search_result_limit"),
        (
            "os29_code_search",
            {"pattern": "x", "search_path": "x.txt"},
            "search_directory_not_found",
        ),
    ):
        with pytest.raises(PolicyDenied, match=reason) as error:
            policy.prepare(name, args)
        assert str(error.value) == reason
    with pytest.raises(PolicyDenied, match="file_size_limit") as error:
        bounded_file_read(str(target), 3)
    assert str(error.value) == "file_size_limit"


def test_literal_search(configure, tmp_path):
    policy = configure(workspace_root=str(tmp_path), max_file_bytes=32)
    (tmp_path / "a.txt").write_text("Needle\nneedle\n", encoding="utf-8")
    (tmp_path / "b.txt").write_bytes(b"x" * 33)
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "skip").write_text("needle")
    assert policy.prepare("os29_code_search", {"pattern": "needle"})["search_path"] == str(
        tmp_path.resolve()
    )
    result = bounded_literal_search(
        str(tmp_path), "needle", max_results=10, case_sensitive=False, policy=policy
    )
    assert result["match_count"] == 2 and result["truncated"]
    exact = bounded_literal_search(
        str(tmp_path), "needle", max_results=1, case_sensitive=True, policy=policy
    )
    assert exact["match_count"] == 1 and exact["matches"][0]["line"] == 2
    assert exact["truncated"]


def test_command_output(tmp_path):
    result = bounded_command(
        (
            sys.executable,
            "-c",
            "import sys; print('ok'); print('err', file=sys.stderr); sys.exit(7)",
        ),
        str(tmp_path),
        10,
        1024,
    )
    assert result["exit_code"] == 7 and result["reason"] is None
    assert result["stdout"].strip() == "ok" and result["stderr"].strip() == "err"
