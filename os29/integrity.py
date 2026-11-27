"""Versioned, tamper-evident Work Unit journal; not an authentication mechanism."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

SCHEMA = "os29.work_unit.integrity.v1"
GENESIS = "0" * 64
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS work_unit_integrity (
    work_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence >= 1),
    event_id TEXT NOT NULL UNIQUE,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    PRIMARY KEY(work_id, sequence),
    FOREIGN KEY(work_id) REFERENCES mission_capsules(mission_id),
    FOREIGN KEY(event_id) REFERENCES trace_events(event_id)
);
"""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _entry_hash(
    work_id: str,
    sequence: int,
    event_id: str,
    previous: str,
    event_hash: str,
    state_hash: str,
) -> str:
    return _sha256(
        _canonical(
            [
                SCHEMA,
                work_id,
                sequence,
                event_id,
                previous,
                event_hash,
                state_hash,
            ]
        )
    )


def _capsule(connection: sqlite3.Connection, work_id: str) -> sqlite3.Row | None:
    row = connection.execute(
        """SELECT project, status, capsule_json, updated_at
           FROM mission_capsules WHERE mission_id=?""",
        (work_id,),
    ).fetchone()
    if not isinstance(row, sqlite3.Row):
        return None
    value = json.loads(row["capsule_json"])
    unit = value.get("work_unit") if isinstance(value, dict) else None
    if not isinstance(unit, dict) or unit.get("schema") != "os29.work_unit.v1":
        return None
    if unit.get("work_id") != work_id:
        return None
    return row


def _state_hash(row: sqlite3.Row) -> str:
    return _sha256(
        _canonical(
            [
                row["project"],
                row["status"],
                row["capsule_json"],
                row["updated_at"],
            ]
        )
    )


def append_entry(
    connection: sqlite3.Connection,
    value: dict[str, Any],
    event_json: str,
    redactions: int,
) -> None:
    """Append inside the caller's transaction, after the corresponding event."""
    work_id = value["trace_id"]
    if not value["kind"].startswith("work_unit.") or value.get("mission_id") != work_id:
        return
    capsule = _capsule(connection, work_id)
    if capsule is None:
        return
    head = connection.execute(
        """SELECT sequence, entry_hash FROM work_unit_integrity
           WHERE work_id=? ORDER BY sequence DESC LIMIT 1""",
        (work_id,),
    ).fetchone()
    sequence = int(head["sequence"]) + 1 if head else 1
    previous = str(head["entry_hash"]) if head else GENESIS
    event_id = value["event_id"]
    event_hash = _sha256(_canonical([event_json, redactions]))
    state_hash = _state_hash(capsule)
    digest = _entry_hash(work_id, sequence, event_id, previous, event_hash, state_hash)
    connection.execute(
        """INSERT INTO work_unit_integrity
           (work_id, sequence, event_id, previous_hash, event_hash, state_hash, entry_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (work_id, sequence, event_id, previous, event_hash, state_hash, digest),
    )


def verify_chain(
    connection: sqlite3.Connection, work_id: str, expected_head: str | None = None
) -> dict[str, Any]:
    """Verify a consistent SQLite snapshot and an optional external anchor.

    Pre-chain history is reported as incomplete, never silently certified.
    This detects changes relative to stored hashes; a trusted external head is
    required to detect an attacker with the ability to rewrite the entire chain.
    """
    if expected_head is not None:
        if re.fullmatch(r"[0-9a-fA-F]{64}", expected_head) is None:
            raise ValueError("expected head must be a 64-character SHA-256 hex digest")
        expected_head = expected_head.lower()
    errors: list[str] = []
    try:
        capsule = _capsule(connection, work_id)
    except (ValueError, TypeError, KeyError):
        capsule = None
    if capsule is None:
        errors.append("missing_or_invalid_work_unit")
    entries = connection.execute(
        """SELECT sequence, event_id, previous_hash, event_hash, state_hash, entry_hash
           FROM work_unit_integrity WHERE work_id=? ORDER BY sequence""",
        (work_id,),
    ).fetchall()
    # Include chain events even if trace metadata has been tampered with.
    events = connection.execute(
        """SELECT *
           FROM trace_events
           WHERE (trace_id=? AND kind LIKE 'work_unit.%')
              OR event_id IN (SELECT event_id FROM work_unit_integrity WHERE work_id=?)""",
        (work_id, work_id),
    ).fetchall()
    indexed = {row["event_id"]: row for row in events}
    chained = {entry["event_id"] for entry in entries}
    if not entries:
        errors.append("unsealed_history")
    if set(indexed) != chained:
        errors.append("missing_or_unsealed_events")
    previous = GENESIS
    for expected_sequence, entry in enumerate(entries, start=1):
        raw_sequence = entry["sequence"]
        if type(raw_sequence) is not int:
            errors.append(f"invalid_sequence:{expected_sequence}")
            sequence = expected_sequence
        else:
            sequence = raw_sequence
        event_id = str(entry["event_id"])
        if sequence != expected_sequence or entry["previous_hash"] != previous:
            errors.append(f"broken_link:{sequence}")
        event = indexed.get(event_id)
        if event is None:
            errors.append(f"missing_event:{sequence}")
        else:
            if (
                not isinstance(event["event_json"], str)
                or type(event["redaction_count"]) is not int
            ):
                errors.append(f"invalid_event_storage:{sequence}")
            elif (
                _sha256(_canonical([event["event_json"], event["redaction_count"]]))
                != entry["event_hash"]
            ):
                errors.append(f"event_hash_mismatch:{sequence}")
            try:
                payload = json.loads(event["event_json"])
                if (
                    not isinstance(payload, dict)
                    or payload.get("event_id") != event_id
                    or payload.get("trace_id") != work_id
                    or payload.get("mission_id") != work_id
                    or event["trace_id"] != work_id
                    or event["mission_id"] != work_id
                    or any(
                        payload.get(field) != event[field]
                        for field in (
                            "kind",
                            "parent_event_id",
                            "timestamp",
                            "source",
                            "component",
                            "action",
                            "outcome",
                            "target",
                            "duration_ms",
                        )
                    )
                ):
                    errors.append(f"event_metadata_mismatch:{sequence}")
            except (ValueError, TypeError):
                errors.append(f"invalid_event_json:{sequence}")
        digest = _entry_hash(
            work_id,
            sequence,
            event_id,
            str(entry["previous_hash"]),
            str(entry["event_hash"]),
            str(entry["state_hash"]),
        )
        if digest != str(entry["entry_hash"]):
            errors.append(f"entry_hash_mismatch:{sequence}")
        previous = str(entry["entry_hash"])
    if entries and capsule is not None:
        try:
            if _state_hash(capsule) != entries[-1]["state_hash"]:
                errors.append("current_state_hash_mismatch")
        except (ValueError, TypeError):
            errors.append("invalid_state_storage")
    if expected_head is not None and previous != expected_head:
        errors.append("external_anchor_mismatch")
    return {
        "schema": SCHEMA,
        "work_id": work_id,
        "valid": not errors,
        "entry_count": len(entries),
        "event_count": len(events),
        "head_hash": previous if entries else None,
        "external_anchor_checked": expected_head is not None,
        "errors": errors,
    }
