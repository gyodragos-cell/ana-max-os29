"""Coverage tests for os29.store sessions/errors, os29.retrieval sources, and os29.telemetry."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from os29 import telemetry
from os29.models import TraceEvent
from os29.retrieval import refresh_memory_index, search_memory
from os29.store import Store


def test_store_sessions_validation_immutability_and_read_only(tmp_path: Path) -> None:
    db = tmp_path / "store.db"
    store = Store(db)

    with pytest.raises(ValueError):
        store.save_session_record(" ", {"title": "a", "summary": "b"})
    with pytest.raises(ValueError):
        store.save_session_record("s1", {"title": "a", "summary": "b"}, source="bad")
    with pytest.raises(ValueError):
        store.save_session_record("s1", "not-a-dict")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        store.save_session_record("s1", {"title": "a", "summary": "b", "unknown": 1})
    with pytest.raises(ValueError):
        store.save_session_record("s1", {"title": "", "summary": "b"})
    with pytest.raises(ValueError):
        store.save_session_record("s1", {"title": "a", "summary": "b", "tags": "bad"})
    with pytest.raises(ValueError):
        store.save_session_record("s1", {"title": "a", "summary": "b"}, ended_at=123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        store.save_session_record("s1", {"title": "a", "summary": "b"}, ended_at="not-iso")

    first = store.save_session_record(
        "s1",
        {"title": "T", "summary": "S token=abc1234567890", "tags": ["a"]},
        ended_at="2026-11-27T01:00:00Z",
    )
    assert first["idempotent_replay"] is False
    replay = store.save_session_record(
        "s1",
        {"title": "T", "summary": "S token=abc1234567890", "tags": ["a"]},
        ended_at="2026-11-27T01:00:00Z",
    )
    assert replay["idempotent_replay"] is True
    with pytest.raises(ValueError, match="immutable"):
        store.save_session_record("s1", {"title": "Changed", "summary": "S"})

    assert store.get_session_record("s1") is not None
    assert store.get_session_record("missing") is None
    assert len(store.list_session_records(limit=5)) == 1

    ro = Store(db, read_only=True)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        ro.record_event(
            TraceEvent(
                trace_id="t",
                source="s",
                component="c",
                kind="diagnostic",
                action="a",
                outcome="observed",
            )
        )
    with pytest.raises(sqlite3.OperationalError), ro._connect() as conn:
        conn.execute("INSERT INTO mission_capsules VALUES ('x','p','s','{}','now')")


def test_retrieval_local_sources_and_filters(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / "config").mkdir(parents=True)
    (workspace / "notes").mkdir(parents=True)
    (workspace / "notes" / "guide.md").write_text(
        "# Heading\n\nParagraph about sqlite wal durability.\n\n" + ("x" * 8100),
        encoding="utf-8",
    )
    (workspace / "notes" / "extra.txt").write_text("alpha beta gamma", encoding="utf-8")
    (workspace / "notes" / "empty.md").write_text("", encoding="utf-8")
    (workspace / "config" / "memory_sources.json").write_text(
        json.dumps(
            {
                "limits": {
                    "max_file_bytes": 50000,
                    "max_total_source_bytes": 200000,
                    "max_files": 10,
                },
                "files": ["notes/extra.txt", "notes/empty.md", "notes/missing.md"],
                "directories": [{"path": "notes", "extensions": [".md"]}],
            }
        ),
        encoding="utf-8",
    )

    store = Store(workspace / "os29.db")
    store.save_session_record("sr-1", {"title": "Session Doc", "summary": "sqlite wal session"})
    refreshed = refresh_memory_index(store)
    assert refreshed["source_counts"].get("document", 0) >= 2

    res = search_memory(store, "sqlite wal", source_types=["document", "session"], refresh=False)
    assert res["result_count"] >= 2
    with pytest.raises(ValueError, match="non-empty"):
        search_memory(store, "   ")


def test_telemetry_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_path = tmp_path / "live.log"
    archive_dir = tmp_path / "archive"
    monkeypatch.setattr(telemetry, "SESSION_LOG", log_path)
    old_handlers = list(telemetry._log.handlers)
    handler = telemetry._AppendRotatingHandler(log_path, max_bytes=200, backup_count=2)
    monkeypatch.setattr(telemetry, "_handler", handler)
    telemetry._log.handlers = [handler]

    try:
        safe = telemetry._sanitize_exc(RuntimeError("failed password=supersecretvalue trace"))
        assert "[REDACTED]" in safe and "supersecretvalue" not in safe

        telemetry.log_startup("srv", "db")
        telemetry.log_auth("os29_status", "readonly", True)
        telemetry.log_auth("os29_terminal_exec", "readonly", False)
        telemetry.log_error("os29_status", RuntimeError("token=secret123"), trace_id="t-1")
        telemetry.log_shutdown()
        assert len(list(archive_dir.glob("live.*.log"))) >= 1
    finally:
        telemetry._log.handlers = old_handlers
        handler.close()
