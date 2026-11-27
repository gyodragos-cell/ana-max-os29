# FILE: tests/test_integrity_full.py
import hashlib
import json
import re

import pytest

from os29.integrity import GENESIS, _canonical, _entry_hash, _sha256, append_entry, verify_chain
from os29.store import Store


@pytest.mark.parametrize("value", [None, {}, {"work_id": "w", "body": "x" * 10240}])
def test_hash_matches_sha256(value):
    expected = json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    digest = _sha256(_canonical(value))
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == hashlib.sha256(expected.encode("utf-8")).hexdigest()


def test_hash_determinism_and_tampering():
    unit = {"work_id": "w", "state": {"step": 1}, "status": "open"}
    digest = _sha256(_canonical(unit))
    assert digest == _sha256(_canonical(dict(reversed(list(unit.items())))))
    for field, changed in (("work_id", "v"), ("state", {"step": 2}), ("status", "done")):
        assert digest != _sha256(_canonical({**unit, field: changed}))


def test_entry_hash_includes_previous():
    first = _entry_hash("w", 1, "e1", GENESIS, "a", "b")
    second = _entry_hash("w", 2, "e2", first, "c", "d")
    assert second == _entry_hash("w", 2, "e2", first, "c", "d")
    assert second != _entry_hash("w", 2, "e2", GENESIS, "c", "d")


@pytest.fixture
def journal(tmp_path):
    store = Store(tmp_path / "integrity.db")
    with store._connect() as conn:
        capsule = {"work_unit": {"schema": "os29.work_unit.v1", "work_id": "w"}}
        conn.execute(
            "INSERT INTO mission_capsules VALUES (?, ?, ?, ?, ?)",
            ("w", "test", "open", json.dumps(capsule), "now"),
        )
        for n in range(1, 11):
            event = {
                "event_id": f"e{n}",
                "trace_id": "w",
                "mission_id": "w",
                "kind": "work_unit.test",
                "timestamp": "now",
                "source": "test",
                "component": "test",
                "action": "check",
                "outcome": "observed",
            }
            payload = json.dumps(event)
            conn.execute(
                "INSERT INTO trace_events (event_id, trace_id, mission_id, kind, "
                "timestamp, source, component, action, outcome, event_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*event.values(), payload),
            )
            append_entry(conn, event, payload, 0)
        yield conn


def test_ten_entry_chain(journal):
    rows = journal.execute("SELECT * FROM work_unit_integrity ORDER BY sequence").fetchall()
    assert len(rows) == 10
    previous = GENESIS
    for i, row in enumerate(rows, 1):
        assert row["sequence"] == i
        assert row["previous_hash"] == previous
        assert row["entry_hash"] == _entry_hash(
            "w", i, row["event_id"], previous, row["event_hash"], row["state_hash"]
        )
        previous = row["entry_hash"]
    result = verify_chain(journal, "w", previous.upper())
    assert result["valid"] and result["errors"] == []
    assert result["entry_count"] == result["event_count"] == 10
    assert result["external_anchor_checked"] and result["head_hash"] == previous


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("UPDATE work_unit_integrity SET previous_hash='bad' WHERE sequence=5", "broken_link:5"),
        ("UPDATE work_unit_integrity SET entry_hash='bad' WHERE sequence=5", "broken_link:6"),
        ("UPDATE trace_events SET event_json='{' WHERE event_id='e5'", "invalid_event_json:5"),
        (
            "UPDATE trace_events SET redaction_count='bad' WHERE event_id='e5'",
            "invalid_event_storage:5",
        ),
        ("UPDATE trace_events SET event_json='{}' WHERE event_id='e5'", "event_hash_mismatch:5"),
        ("UPDATE mission_capsules SET capsule_json='null'", "missing_or_invalid_work_unit"),
        ("UPDATE mission_capsules SET capsule_json='{'", "missing_or_invalid_work_unit"),
        (
            "UPDATE mission_capsules SET capsule_json='{\"work_unit\":{}}'",
            "missing_or_invalid_work_unit",
        ),
        (
            'UPDATE mission_capsules SET capsule_json=\'{"work_unit":{"schema":"os29.work_unit.v1","work_id":"other"}}\'',
            "missing_or_invalid_work_unit",
        ),
        ("UPDATE mission_capsules SET status='changed'", "current_state_hash_mismatch"),
    ],
)
def test_corrupted_chain(journal, sql, expected):
    journal.execute(sql)
    result = verify_chain(journal, "w")
    assert not result["valid"]
    assert expected in result["errors"]


def test_invalid_sequence(journal):
    # A malformed sequence in the isolated journal.
    journal.execute("UPDATE work_unit_integrity SET sequence=5.5 WHERE sequence=5")
    result = verify_chain(journal, "w")
    assert "invalid_sequence:5" in result["errors"]


def test_append_ignores_unrelated_or_missing_capsule(journal):
    for event in (
        {"trace_id": "w", "kind": "diagnostic", "mission_id": "w"},
        {"trace_id": "w", "kind": "work_unit.test", "mission_id": "other"},
        {"trace_id": "missing", "kind": "work_unit.test", "mission_id": "missing"},
    ):
        append_entry(journal, event, "{}", 0)
    assert verify_chain(journal, "w")["entry_count"] == 10
    assert "external_anchor_mismatch" in verify_chain(journal, "w", "f" * 64)["errors"]
    with pytest.raises(ValueError, match="64-character") as error:
        verify_chain(journal, "w", "bad")
    assert "SHA-256" in str(error.value)
