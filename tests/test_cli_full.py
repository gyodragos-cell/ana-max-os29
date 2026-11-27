"""Comprehensive CLI coverage tests for os29.cli."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from os29 import cli
from os29.models import TraceEvent
from os29.store import Store
from os29.work_units import WorkUnitService


def _run_cli(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["os29", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert isinstance(exc.value.code, int)
    return exc.value.code


def test_cli_status_demo_trace_capsule_and_experience(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "cli.db"
    assert _run_cli(monkeypatch, ["--db", str(db), "status"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"

    assert _run_cli(monkeypatch, ["--db", str(db), "demo"]) == 0
    demo_out = json.loads(capsys.readouterr().out)
    assert demo_out["result"] == "OS29_DEMO_PASS"
    trace_id = demo_out["trace_id"]

    assert _run_cli(monkeypatch, ["--db", str(db), "trace", trace_id]) == 0
    trace_out = json.loads(capsys.readouterr().out)
    assert len(trace_out["events"]) == 5

    assert _run_cli(monkeypatch, ["--db", str(db), "trace", trace_id, "--diagnose"]) == 0
    diag_out = json.loads(capsys.readouterr().out)
    assert diag_out["trace_id"] == trace_id

    cap_file = tmp_path / "capsule.json"
    cap_file.write_text(
        json.dumps(
            {
                "project": "cli-test",
                "objective": "test capsule save/get",
                "current_state": {"step": 1},
                "known_good": ["ok"],
                "known_bad": [],
                "open_issues": [],
                "next_steps": ["done"],
            }
        ),
        encoding="utf-8",
    )
    assert _run_cli(monkeypatch, ["--db", str(db), "capsule", "save", "m-cli", str(cap_file)]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "capsule", "get", "m-cli"]) == 0
    assert json.loads(capsys.readouterr().out)["mission_id"] == "m-cli"
    assert _run_cli(monkeypatch, ["--db", str(db), "capsule", "get", "missing"]) == 4
    capsys.readouterr()

    bad_cap = tmp_path / "bad_cap.json"
    bad_cap.write_text("[]", encoding="utf-8")
    assert _run_cli(monkeypatch, ["--db", str(db), "capsule", "save", "m-bad", str(bad_cap)]) == 2
    assert "error" in json.loads(capsys.readouterr().err)

    assert _run_cli(monkeypatch, ["--db", str(db), "experience-search", "demo"]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "intelligence", "--event-limit", "50"]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "memory-index"]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "memory-search", "demo"]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "capabilities"]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "capability-edges"]) == 0
    capsys.readouterr()


def test_cli_verify_and_scope_and_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "wu.db"
    service = WorkUnitService(Store(db))
    service.create(
        work_id="wu-cli-1",
        project="p",
        objective="o",
        owner_agent="a",
        allowed_scope=[],
        current_state={"s": 1},
        known_good=[],
        known_bad=[],
        open_issues=[],
        next_steps=[],
        context_refs=[],
    )
    assert _run_cli(monkeypatch, ["--db", str(db), "verify", "wu-cli-1"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["valid"] is True
    assert (
        _run_cli(
            monkeypatch,
            ["--db", str(db), "verify", "wu-cli-1", "--expected-head", res["head_hash"]],
        )
        == 0
    )
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "verify", "wu-missing"]) == 3
    capsys.readouterr()
    assert (
        _run_cli(monkeypatch, ["--db", str(db), "verify", "wu-cli-1", "--expected-head", "bad"])
        == 2
    )
    capsys.readouterr()

    scope_file = tmp_path / "scope.json"
    scope_file.write_text(
        json.dumps(
            {
                "schema_version": "os29.scope.v1",
                "approved_hosts": ["127.0.0.1"],
                "approved_ports": [8080, 8766],
            }
        ),
        encoding="utf-8",
    )
    assert (
        _run_cli(
            monkeypatch,
            [
                "--db",
                str(db),
                "scope-check",
                "http://127.0.0.1:8080/health",
                "--scope",
                str(scope_file),
            ],
        )
        == 0
    )
    capsys.readouterr()
    assert (
        _run_cli(
            monkeypatch,
            ["--db", str(db), "scope-check", "https://example.invalid", "--scope", str(scope_file)],
        )
        == 3
    )
    capsys.readouterr()

    jsonl = tmp_path / "events.jsonl"
    evt = TraceEvent(
        trace_id="t-ing",
        source="cli",
        component="ingest",
        kind="diagnostic",
        action="test_line",
        outcome="observed",
    ).to_dict()
    jsonl.write_text(json.dumps(evt) + "\n\nnot-json\n", encoding="utf-8")
    assert _run_cli(monkeypatch, ["--db", str(db), "ingest-jsonl", str(jsonl)]) == 1
    assert json.loads(capsys.readouterr().out)["ingested"] == 1
    assert (
        _run_cli(monkeypatch, ["--db", str(db), "ingest-jsonl", str(jsonl), "--continue-on-error"])
        == 1
    )
    capsys.readouterr()


def test_cli_sessions_and_import_and_validate_and_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "sess.db"
    sess_file = tmp_path / "sess.json"
    sess_file.write_text(
        json.dumps({"title": "Session 1", "summary": "Completed smoke check"}),
        encoding="utf-8",
    )
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "save", "s-1", str(sess_file)]) == 0
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "get", "s-1"]) == 0
    assert json.loads(capsys.readouterr().out)["session_id"] == "s-1"
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "get", "missing"]) == 4
    capsys.readouterr()
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "list"]) == 0
    assert len(json.loads(capsys.readouterr().out)["sessions"]) == 1
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "resume", "--query", "smoke"]) == 0
    capsys.readouterr()

    bad_sess = tmp_path / "bad_sess.json"
    bad_sess.write_text("[]", encoding="utf-8")
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "save", "s-bad", str(bad_sess)]) == 2
    capsys.readouterr()

    export_data = [
        "ignore-non-dict",
        {
            "id": "conv-1",
            "title": "Exported Chat",
            "current_node": "n2",
            "mapping": {
                "n1": {
                    "parent": None,
                    "message": {"author": {"role": "user"}, "content": {"parts": ["hello"]}},
                },
                "n2": {
                    "parent": "n1",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": [{"text": "world"}]},
                    },
                },
            },
        },
        {
            "id": "conv-2",
            "title": "Fallback Order Chat",
            "mapping": {
                "x1": {"message": {"author": {"role": "user"}, "content": {"parts": ["hi"]}}}
            },
        },
    ]
    export_json = tmp_path / "conversations.json"
    export_json.write_text(json.dumps(export_data), encoding="utf-8")
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "import", str(export_json)]) == 0
    assert json.loads(capsys.readouterr().out)["imported"] == 2

    export_zip = tmp_path / "export.zip"
    with zipfile.ZipFile(export_zip, "w") as zf:
        zf.writestr("conversations.json", json.dumps({"conversations": export_data[1:2]}))
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "import", str(export_zip)]) == 0
    capsys.readouterr()

    empty_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("other.txt", "none")
    assert _run_cli(monkeypatch, ["--db", str(db), "session", "import", str(empty_zip)]) == 2
    capsys.readouterr()

    store = Store(db)
    ev = store.record_event(
        TraceEvent(
            trace_id="t-val",
            source="test",
            component="cli",
            kind="test.completed",
            action="verify",
            outcome="success",
            attributes={"ground_truth": "verified"},
        )
    )
    cand = store.record_experience(
        problem_key="p",
        cause="c",
        solution="s",
        outcome="partial",
        source_event_ids=[ev["event_id"]],
        outcome_verified=False,
        confidence=0.2,
    )

    class FakeTTY(io.StringIO):
        def isatty(self) -> bool:
            return True

    stdin_before, stdout_before = cli.sys.stdin, cli.sys.stdout
    tty_stdout = FakeTTY()
    monkeypatch.setattr(cli.sys, "stdin", FakeTTY())
    monkeypatch.setattr(cli.sys, "stdout", tty_stdout)
    answers = iter(["operator-1", "NOPE"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert (
        _run_cli(
            monkeypatch,
            ["--db", str(db), "experience-validate", cand["lesson_id"], ev["event_id"]],
        )
        == 5
    )
    capsys.readouterr()

    answers_ok = iter(["operator-1", f"VALIDATE {cand['lesson_id']}"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers_ok))
    assert (
        _run_cli(
            monkeypatch,
            ["--db", str(db), "experience-validate", cand["lesson_id"], ev["event_id"]],
        )
        == 0
    )
    assert "EXPERIENCE_VALIDATED" in tty_stdout.getvalue()
    assert store.get_experience(cand["lesson_id"])["status"] == "validated"
    monkeypatch.setattr(cli.sys, "stdin", stdin_before)
    monkeypatch.setattr(cli.sys, "stdout", stdout_before)

    with patch("os29.cli.snapshot_loopback", return_value={"status": "complete"}):
        assert _run_cli(monkeypatch, ["--db", str(db), "snapshot"]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "complete"

    with patch(
        "os29.cli.answer_from_memory",
        return_value={"answer_status": "grounded", "answer": "ok"},
    ):
        assert _run_cli(monkeypatch, ["--db", str(db), "memory-answer", "hello"]) == 0
        capsys.readouterr()
    with patch(
        "os29.cli.answer_from_memory", return_value={"answer_status": "evidence_insufficient"}
    ):
        assert _run_cli(monkeypatch, ["--db", str(db), "memory-answer", "hello"]) == 4
        capsys.readouterr()
    with patch("os29.cli.answer_from_memory", return_value={"answer_status": "needs_review"}):
        assert _run_cli(monkeypatch, ["--db", str(db), "memory-answer", "hello"]) == 5
        capsys.readouterr()
    with patch("os29.cli.answer_from_memory", return_value={"answer_status": "error"}):
        assert _run_cli(monkeypatch, ["--db", str(db), "memory-answer", "hello"]) == 6
        capsys.readouterr()
