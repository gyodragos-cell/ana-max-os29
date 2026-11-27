"""Build a wheel, install it offline into a new venv, verify CLI and MCP."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(argv, cwd, env, expected=0, stdin=None):
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"exit={result.returncode}, expected={expected}: {result.stderr}\n{result.stdout}"
        )
    return result.stdout


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="os29-wheel-") as temp:
        folder = Path(temp)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("OS29_") and k not in {"PYTHONPATH", "PYTHONHOME"}
        }
        env.update(
            {
                "PYTHONUTF8": "1",
                "OS29_DB_PATH": str(folder / "sample.db"),
                "OS29_LOG_DIR": str(folder / "runtime-logs"),
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }
        )
        run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(folder), "."],
            root,
            env,
        )
        (wheel,) = folder.glob("*.whl")
        run([sys.executable, "-m", "venv", str(folder / "venv")], folder, env)
        py = str(folder / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        run([py, "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], folder, env)
        for target, expected in (("http://localhost:7777", 0), ("http://localhost:8080", 3)):
            out = run([py, "-m", "os29.cli", "scope-check", target], folder, env, expected)
            assert json.loads(out)["allowed"] == (expected == 0), out
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "os29_scope_check",
                    "arguments": {"target": "http://localhost:7777"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "os29_scope_check",
                    "arguments": {"target": "http://localhost:8080"},
                },
            },
        ]
        raw = run(
            [py, "-m", "os29.mcp_stdio"],
            folder,
            env,
            stdin="".join(json.dumps(m) + "\n" for m in messages),
        )
        responses = {m["id"]: m for m in map(json.loads, raw.splitlines())}
        for n, allowed in ((2, True), (3, False)):
            result = responses[n]["result"]
            assert not result.get("isError"), result
            decision = json.loads(result["content"][0]["text"])
            assert decision["allowed"] is allowed, decision
        print("WHEEL_STANDALONE_PASS cli=2 mcp=2 offline_install=true")


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Run without Python -O")
    main()
