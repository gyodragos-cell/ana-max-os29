#!/usr/bin/env python3
"""
OS29 Crash Recovery Chaos Test
Launches 5 worker processes; some call os._exit(0) right after writing.
Verifies the SQLite WAL DB remains intact (no corruption, all committed rows readable).
Run: py -3.12 examples/02_crash_recovery_chaos.py
"""

from __future__ import annotations

import json
import multiprocessing
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Worker functions — each lives in a separate process
# ---------------------------------------------------------------------------


def worker_normal(db_path: str, worker_id: int) -> None:
    """Writes an event, then exits normally."""
    sys.path.insert(0, str(ROOT))
    from os29.store import Store
    from os29.models import TraceEvent

    store = Store(db_path)
    store.record_event(
        TraceEvent(
            trace_id=f"chaos-trace-{worker_id:02d}",
            source="chaos-worker",
            component="crash-chaos",
            kind="task.execution",
            action="normal_write",
            outcome="success",
            attributes={"worker_id": worker_id, "crash": False},
        )
    )
    # Normal exit — WAL checkpoint will happen


def worker_crash_after_write(db_path: str, worker_id: int) -> None:
    """Writes an event, then hard-exits via os._exit(0) (simulates crash)."""
    sys.path.insert(0, str(ROOT))
    from os29.store import Store
    from os29.models import TraceEvent

    store = Store(db_path)
    store.record_event(
        TraceEvent(
            trace_id=f"chaos-trace-{worker_id:02d}",
            source="chaos-worker",
            component="crash-chaos",
            kind="task.execution",
            action="crash_after_write",
            outcome="success",
            attributes={"worker_id": worker_id, "crash": True},
        )
    )
    os._exit(0)  # Hard crash — bypasses Python cleanup, WAL must protect DB


def worker_write_only(db_path: str, worker_id: int) -> None:
    """Writes two events then exits normally — higher write volume."""
    sys.path.insert(0, str(ROOT))
    from os29.store import Store
    from os29.models import TraceEvent

    store = Store(db_path)
    for step in range(2):
        store.record_event(
            TraceEvent(
                trace_id=f"chaos-trace-{worker_id:02d}",
                source="chaos-worker",
                component="crash-chaos",
                kind="task.execution",
                action=f"bulk_write_step_{step}",
                outcome="success",
                attributes={"worker_id": worker_id, "step": step},
            )
        )


# ---------------------------------------------------------------------------
# Chaos plan: 5 processes, 2 crash hard after write
# ---------------------------------------------------------------------------

CHAOS_PLAN = [
    (worker_normal, 0),  # normal exit
    (worker_crash_after_write, 1),  # crash after write  ← WAL must survive
    (worker_write_only, 2),  # 2 events, normal exit
    (worker_crash_after_write, 3),  # crash after write  ← WAL must survive
    (worker_normal, 4),  # normal exit
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "chaos.db")

        # Pre-initialise the DB (creates schema) before spawning workers
        sys.path.insert(0, str(ROOT))
        from os29.store import Store

        store = Store(db_path)

        print(f"[chaos] DB: {db_path}")
        print(
            f"[chaos] Launching {len(CHAOS_PLAN)} workers (2 will os._exit after write)..."
        )

        ctx = multiprocessing.get_context("spawn")
        procs: list[multiprocessing.Process] = []
        for fn, wid in CHAOS_PLAN:
            p = ctx.Process(target=fn, args=(db_path, wid), daemon=False)
            p.start()
            procs.append(p)

        for p in procs:
            p.join(timeout=15)
            if p.is_alive():
                p.kill()
                p.join()

        print("[chaos] All workers finished (or were reaped).")

        # --- Integrity check ---
        # Re-open the DB from the MAIN process and read back all committed events
        store2 = Store(db_path)
        s = store2.stats()
        events = store2.recent_events(limit=1000)

        print(f"[chaos] DB events readable: {s['events']}")
        print(f"[chaos] DB traces:          {s['traces']}")

        # SQLite WAL guarantee: any committed transaction must survive an os._exit crash
        # Workers that called os._exit after store.record_event (which commits inside
        # _connect().__exit__) must have their rows in the DB.
        # Workers 1 and 3 each wrote 1 event before crashing → at least 2 hard-crash rows.
        # Workers 0, 2, 4 wrote 1+2+1=4 events normally → total committed ≥ 6.
        assert s["events"] >= 6, (
            f"Expected ≥6 committed events after chaos, got {s['events']}. "
            "WAL integrity may be compromised."
        )

        component_set = {e.get("component") for e in events}
        assert "crash-chaos" in component_set, "No chaos-worker events found in DB!"

        result = {
            "total_events_in_db": s["events"],
            "total_traces": s["traces"],
            "db_status": s["status"],
            "components_seen": sorted(component_set),
            "hard_crash_workers": [1, 3],
            "integrity_assertion": "PASSED — WAL survived all os._exit crashes",
        }
        print("\n[RESULT JSON]")
        print(json.dumps(result, indent=2))
        print("\n[chaos] PASS — SQLite WAL integrity verified after hard-crash chaos.")


if __name__ == "__main__":
    main()
