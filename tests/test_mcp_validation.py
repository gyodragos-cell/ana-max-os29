"""Protocol validation and bounded framing in the public MCP provider."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from os29 import mcp_stdio
from os29.mcp_validation import MAX_FRAME_BYTES, MAX_OUTPUT_BYTES


def call(name, arguments, identifier=1):
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


@pytest.mark.parametrize(
    "message,code",
    [
        ([], -32600),
        ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, -32600),
        ({"jsonrpc": "2.0", "id": True, "method": "ping"}, -32600),
        ({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": []}, -32602),
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": False},
            },
            -32602,
        ),
    ],
)
def test_invalid_envelope(message, code):
    assert mcp_stdio.handle(message)["error"]["code"] == code


@pytest.mark.parametrize(
    "name,args",
    [
        ("os29_status", {"unexpected": True}),
        ("os29_trace_get", {}),
        ("os29_work_unit_list", {"limit": True}),
        ("os29_work_unit_list", {"limit": 101}),
        ("os29_trace_get", {"trace_id": 12}),
        ("os29_memory_search", {"query": "test", "source_types": ["invalid"]}),
        ("os29_memory_answer", {"query": "x", "timeout_seconds": -1}),
        ("os29_memory_answer", {"query": "x", "limit": 7}),
        ("os29_status", []),
        ("os29_status", None),
    ],
)
def test_bad_arguments_never_create_database(tmp_path, monkeypatch, name, args):
    database = tmp_path / "must-not-exist.db"
    monkeypatch.setattr(mcp_stdio, "DB_PATH", database)
    result = mcp_stdio.handle(call(name, args))
    assert result["result"]["isError"]
    assert not database.exists()


def test_tool_notification_cannot_execute(tmp_path, monkeypatch):
    database = tmp_path / "must-not-exist.db"
    monkeypatch.setattr(mcp_stdio, "DB_PATH", database)
    message = call("os29_status", {})
    del message["id"]
    assert mcp_stdio.handle(message) is None
    assert not database.exists()


def test_response_limit_is_explicit(monkeypatch):
    monkeypatch.setattr(mcp_stdio, "call_tool", lambda *_: {"value": "x" * MAX_OUTPUT_BYTES})
    result = mcp_stdio.handle(call("os29_status", {}))
    assert result["result"]["isError"]
    assert "output exceeds limit" in result["result"]["content"][0]["text"]


def test_real_stdio_rejects_oversized_and_invalid_frames_then_recovers(tmp_path):
    env = os.environ.copy()
    env["OS29_DB_PATH"] = str(tmp_path / "isolated.db")
    env["OS29_LOG_DIR"] = str(tmp_path / "logs")
    frames = [
        b"x" * (MAX_FRAME_BYTES + 16),
        b'{"jsonrpc":"2.0","id":1,"method":"ping","id":2}',
        b'{"jsonrpc":"2.0","id":3,"method":"ping","params":{"x":NaN}}',
        b"\xff",
        b"[" * 100 + b"0" + b"]" * 100,
        b'{"jsonrpc":"2.0","method":"notifications/initialized"}',
        b'{"jsonrpc":"2.0","id":8,"method":"ping"}',
    ]
    result = subprocess.run(
        [sys.executable, "-m", "os29.mcp_stdio"],
        input=b"\n".join(frames) + b"\n",
        env=env,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(replies) == 6
    assert replies[0]["error"]["code"] == -32600
    assert all(reply["error"]["code"] == -32700 for reply in replies[1:5])
    assert replies[5]["id"] == 8 and replies[5]["result"] == {}
    assert not (tmp_path / "isolated.db").exists()
