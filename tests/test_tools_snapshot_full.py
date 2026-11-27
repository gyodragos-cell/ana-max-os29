"""Coverage tests for os29.tools and os29.runtime_snapshot."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from os29 import runtime_snapshot, tools
from os29.store import Store


def test_terminal_exec_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert tools.terminal_exec("")["exit_code"] == 1

    store = Store(tmp_path / "tools.db")
    ok = tools.terminal_exec(
        f'"{sys.executable}" -c "print(123)"',
        cwd=str(tmp_path),
        store=store,
        trace_id="term-ok",
    )
    assert ok["exit_code"] == 0 and "123" in ok["stdout"]
    assert len(store.list_trace("term-ok")) == 1

    def raise_timeout(*_a: object, **_k: object) -> object:
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(tools.subprocess, "run", raise_timeout)
    t_out = tools.terminal_exec("slow", timeout_seconds=1, store=store, trace_id="term-to")
    assert t_out["exit_code"] == -1 and "timed out" in t_out["stderr"]

    def raise_os(*_a: object, **_k: object) -> object:
        raise OSError("boom")

    monkeypatch.setattr(tools.subprocess, "run", raise_os)
    err = tools.terminal_exec("bad", store=store, trace_id="term-err")
    assert err["exit_code"] == -1 and "boom" in err["stderr"]


def test_file_tools_and_code_search(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "hello.txt"
    w = tools.file_write(str(target), "line1\nneedle\nline3\n")
    assert w["success"] is True

    with pytest.raises(FileExistsError):
        tools.file_write(str(target), "dup", overwrite=False)

    r = tools.file_read(str(target), start_line=2, end_line=2)
    assert r["total_lines"] == 3 and r["content"] == "needle"

    with pytest.raises(FileNotFoundError):
        tools.file_read(str(tmp_path / "missing.txt"))

    skip_dir = tmp_path / "__pycache__"
    skip_dir.mkdir()
    (skip_dir / "ignored.py").write_text("needle", encoding="utf-8")

    search = tools.code_search("needle", search_path=str(tmp_path), max_results=1)
    assert search["match_count"] == 1
    assert "ignored.py" not in search["matches"][0]["file"]

    with pytest.raises(NotADirectoryError):
        tools.code_search("needle", search_path=str(target))


def test_runtime_snapshot_mocked_psutil_and_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProc:
        def __init__(self, pid: int) -> None:
            if pid == 999:
                raise OSError("gone")

        def name(self) -> str:
            return "python.exe"

    fake_psutil = SimpleNamespace(
        CONN_LISTEN="LISTEN",
        Error=RuntimeError,
        Process=FakeProc,
        net_connections=lambda kind="tcp": [
            SimpleNamespace(status="ESTABLISHED", laddr=None, pid=1),
            SimpleNamespace(
                status="LISTEN",
                laddr=SimpleNamespace(port=8766, ip="0.0.0.0"),
                pid=101,
            ),
            SimpleNamespace(
                status="LISTEN",
                laddr=SimpleNamespace(port=11434, ip="127.0.0.1"),
                pid=999,
            ),
        ],
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    lmap = runtime_snapshot._listener_map()
    assert lmap[8766][0]["process_name"] == "python.exe"
    assert lmap[11434][0]["process_name"] == "unavailable"

    class FakeResp:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self, _n: int = -1) -> bytes:
            return self._body

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    def fake_urlopen(req: object, timeout: float = 1.0) -> FakeResp:
        url = getattr(req, "full_url", "")
        if "11434" in url:
            return FakeResp(200, json.dumps({"models": [{"name": "qwen"}]}).encode())
        if "8766" in url:
            return FakeResp(200, json.dumps({"status": "ok", "agent": "ana"}).encode())
        if "8771" in url:
            raise HTTPError(url, 403, "Forbidden", None, None)  # type: ignore[arg-type]
        if "8772" in url:
            return FakeResp(200, json.dumps(["non-dict"]).encode())
        raise URLError("offline")

    store = Store(tmp_path / "snap.db")
    with patch("os29.runtime_snapshot.urlopen", side_effect=fake_urlopen):
        snap = runtime_snapshot.snapshot_loopback(store, timeout=0.1)

    assert snap["status"] == "complete"
    assert any(
        r["port"] == 8766 and r["reason"] == "wildcard_listener" for r in snap["exposure_risks"]
    )
    assert len(snap["services"]) == len(runtime_snapshot.SERVICES)

    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            Error=RuntimeError,
            net_connections=lambda kind="tcp": (_ for _ in ()).throw(OSError("denied")),
        ),
    )
    assert runtime_snapshot._listener_map() == {}
