"""Read-only adapter for Anti-Repeat Planner V1.

The adapter accepts caller-provided records and bounded JSON files only. It never
opens network connections, calls MCP/tools, writes files, or touches the OS29 DB.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .anti_repeat import evaluate


def evaluate_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one already-loaded factual record without side effects."""
    return evaluate(record)


def evaluate_json_file(path: str | Path, max_bytes: int = 256_000) -> dict[str, Any]:
    """Read one bounded local JSON fixture/report and classify it.

    This is intentionally read-only and restricted to regular files. It does not
    resolve paths against a workspace or invoke any external component.
    """
    candidate = Path(path)
    if not candidate.is_file():
        return {"status": "REQUIRES_REVIEW", "current_blocker": "fixture_not_found", "next_action": "provide an existing JSON fixture"}
    if candidate.stat().st_size > max_bytes:
        return {"status": "REQUIRES_REVIEW", "current_blocker": "fixture_too_large", "next_action": "provide a bounded fixture"}
    try:
        record = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"status": "REQUIRES_REVIEW", "current_blocker": f"fixture_invalid:{type(exc).__name__}", "next_action": "repair fixture JSON"}
    if not isinstance(record, dict):
        return {"status": "REQUIRES_REVIEW", "current_blocker": "fixture_must_be_object", "next_action": "provide an object fixture"}
    return evaluate(record)
