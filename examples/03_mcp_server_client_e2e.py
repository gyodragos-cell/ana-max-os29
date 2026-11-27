#!/usr/bin/env python3
"""
OS29 Example 03 — End-to-End MCP STDIO Server + Policy Guard
Spawns `python -m os29.mcp_stdio` over STDIO, executes verified Work Unit calls,
triggers a PolicyDenied block on an unapproved command, and inspects the audit trace.

Run: python examples/03_mcp_server_client_e2e.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def rpc(
    proc: subprocess.Popen[str], req_id: int, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    assert proc.stdin is not None and proc.stdout is not None
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"MCP STDIO server closed unexpectedly: {stderr}")
    return json.loads(line)


def call_tool(
    proc: subprocess.Popen[str], req_id: int, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    resp = rpc(proc, req_id, "tools/call", {"name": name, "arguments": arguments})
    text = resp["result"]["content"][0]["text"]
    return {"isError": resp["result"].get("isError", False), "data": json.loads(text)}


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        db_path = tmp_dir / "mcp_e2e.db"
        policy_path = tmp_dir / "policy.json"
        policy_path.write_text(
            json.dumps(
                {
                    "mode": "normal",
                    "workspace_root": str(tmp_dir),
                    "deny_tools": ["os29_file_write"],
                }
            ),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["OS29_DB_PATH"] = str(db_path)
        env["OS29_MCP_POLICY_FILE"] = str(policy_path)
        env["PYTHONPATH"] = str(ROOT)

        proc = subprocess.Popen(
            [sys.executable, "-m", "os29.mcp_stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(ROOT),
            env=env,
        )
        try:
            init_resp = rpc(proc, 1, "initialize", {})
            assert init_resp["result"]["serverInfo"]["name"] == "os29-operational-intelligence"

            tools_resp = rpc(proc, 2, "tools/list", {})
            tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
            assert "os29_work_unit_verify" in tool_names

            created = call_tool(
                proc,
                3,
                "os29_work_unit_create",
                {
                    "work_id": "wu-mcp-e2e-001",
                    "project": "mcp-e2e",
                    "objective": "Verify STDIO JSON-RPC and policy enforcement",
                    "owner_agent": "client-a",
                    "allowed_scope": ["local"],
                    "current_state": {"step": "created"},
                    "known_good": ["stdio initialized"],
                    "known_bad": [],
                    "open_issues": [],
                    "next_steps": ["record evidence", "verify hash chain"],
                    "context_refs": [],
                },
            )
            assert not created["isError"]

            receipt = call_tool(
                proc,
                4,
                "os29_evidence_receipt_record",
                {
                    "work_id": "wu-mcp-e2e-001",
                    "actor_agent": "client-a",
                    "action": "verify_stdio_handshake",
                    "outcome": "success",
                    "evidence": {"tools_discovered": len(tool_names)},
                    "next_action": "verify chain",
                },
            )
            assert not receipt["isError"]

            blocked_write = call_tool(
                proc,
                5,
                "os29_file_write",
                {"path": "blocked.txt", "content": "should not write"},
            )
            assert blocked_write["isError"] is True
            assert blocked_write["data"]["error"] == "tool_not_allowed"

            blocked_cmd = call_tool(
                proc,
                6,
                "os29_terminal_exec",
                {"command": "unapproved_alias"},
            )
            assert blocked_cmd["isError"] is True
            assert blocked_cmd["data"]["error"] == "command_alias_not_approved"

            verified = call_tool(
                proc,
                7,
                "os29_work_unit_verify",
                {"work_id": "wu-mcp-e2e-001"},
            )
            assert verified["data"]["valid"] is True
            assert verified["data"]["entry_count"] == 2

            summary = {
                "protocol_version": init_resp["result"]["protocolVersion"],
                "tools_count": len(tool_names),
                "blocked_write": blocked_write["data"]["error"],
                "blocked_cmd": blocked_cmd["data"]["error"],
                "chain_valid": verified["data"]["valid"],
                "entry_count": verified["data"]["entry_count"],
                "head_hash": verified["data"]["head_hash"],
            }
            print(json.dumps(summary, indent=2))
        finally:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10)


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Run verification examples without Python -O")
    main()
