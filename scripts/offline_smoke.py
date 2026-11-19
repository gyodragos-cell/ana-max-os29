"""Independent local SQLite and OS28 mock smoke; no live dependencies."""
from __future__ import annotations
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from os29.store import Store
from os29.work_units import WorkUnitService
from integrations.os28 import MockOS28Provider


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="os29-public-smoke-") as temp:
        db = Path(temp) / "test.db"
        svc = WorkUnitService(Store(db))
        svc.create(
            work_id="public-smoke-001",
            project="offline-example",
            objective="Resume from an ID",
            owner_agent="agent-a",
            allowed_scope=["temporary local SQLite store"],
            current_state={"step": 1},
            known_good=[], known_bad=[], open_issues=[],
            next_steps=["Read stored context"], context_refs=[]
        )
        resumed = WorkUnitService(Store(db)).resume(
            work_id="public-smoke-001", agent_id="agent-b"
        )
        assert resumed["work_id"] == "public-smoke-001"
        assert resumed["objective"] == "Resume from an ID"
        mock = MockOS28Provider()
        assert mock.call("example.echo", {"text": "pass"}) == {"text": "pass", "mock": True}
        print("OFFLINE_SMOKE_PASS work_unit_resume=1 mock_os28=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
