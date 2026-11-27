#!/usr/bin/env python3
"""
OS29 Quickstart — Work Unit Example
Demonstrates: Store creation, record_event, stats(), save_capsule, get_capsule.
Run: py -3.12 examples/01_quickstart_work_unit.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from os29.store import Store
from os29.models import TraceEvent


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "quickstart.db"
        store = Store(db_path)

        # --- 1. Record a TraceEvent ---
        event = TraceEvent(
            trace_id="trace-quickstart-001",
            source="example-agent",
            component="quickstart",
            kind="task.execution",
            action="run_work_unit",
            outcome="success",
            duration_ms=42.5,
            attributes={"step": 1, "label": "OS29 quickstart demo"},
        )
        result = store.record_event(event)
        print(
            f"[record_event] event_id={result['event_id']}  redactions={result['redactions']}"
        )

        # --- 2. Verify stats() shows event_count > 0 ---
        s = store.stats()
        assert s["events"] > 0, f"Expected events>0, got {s['events']}"
        print(
            f"[stats] events={s['events']}  traces={s['traces']}  status={s['status']}"
        )

        # --- 3. Save a mission capsule ---
        capsule_data = {
            "project": "OS29 Lab Demo",
            "objective": "Demonstrate Store API in a reproducible quickstart.",
            "current_state": "Example script running successfully.",
            "status": "active",
            "known_good": ["record_event works", "stats returns event_count>0"],
            "known_bad": [],
            "open_issues": [],
            "next_steps": ["Run 02_crash_recovery_chaos.py"],
        }
        saved = store.save_capsule("mission-quickstart-001", capsule_data)
        print(
            f"[save_capsule] mission_id={saved['mission_id']}  updated_at={saved['updated_at']}"
        )

        # --- 4. Retrieve the capsule ---
        retrieved = store.get_capsule("mission-quickstart-001")
        assert retrieved is not None, "Capsule not found after save!"
        print(f"[get_capsule] project={retrieved['capsule']['project']}")

        # --- 5. Final JSON summary ---
        summary = {
            "event_id": result["event_id"],
            "trace_id": "trace-quickstart-001",
            "stats": s,
            "capsule_mission_id": retrieved["mission_id"],
            "capsule_project": retrieved["capsule"]["project"],
            "all_assertions_passed": True,
        }
        print("\n[RESULT JSON]")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
