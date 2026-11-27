"""Reproducible three-process handoff using a disposable synthetic defect.

This is not a live test of three AI models. Each role runs in a fresh Python
process, retrieves state from SQLite, and executes a real fixture regression.
No private lab files, models, network calls, or fabricated test output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from os29.store import Store  # noqa: E402
from os29.work_units import WorkUnitService  # noqa: E402

WORK_ID = "wu-process-handoff-demo"
CHECK = """from fixture import window_handle
assert window_handle({'pid': 123, 'hwnd': 456}) == 456
print('fixture regression PASS')
"""


def run_check(folder: Path) -> dict:
    result = subprocess.run(
        [sys.executable, "check_fixture.py"],
        cwd=folder,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return {
        "command": "python check_fixture.py",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(
    service: WorkUnitService,
    work_id: str,
    agent: str,
    action: str,
    evidence: dict,
    next_action: str,
) -> None:
    service.record_evidence_receipt(
        work_id=work_id,
        actor_agent=agent,
        action=action,
        outcome="success" if evidence["exit_code"] == 0 else "failure",
        evidence=evidence,
        next_action=next_action,
    )


def role_a(db: Path, work_id: str) -> dict:
    store = Store(db)
    service = WorkUnitService(store)
    folder = db.parent
    fixture = folder / "fixture.py"
    fixture.write_text("def window_handle(row):\n    return row['pid']\n", encoding="utf-8")
    (folder / "check_fixture.py").write_text(CHECK, encoding="utf-8")
    service.create(
        work_id=work_id,
        project="Synthetic handle regression",
        objective="Return the window handle rather than the process ID",
        owner_agent="role-a",
        allowed_scope=["fixture.py", "check_fixture.py"],
        current_state={"fixture": "fixture.py", "test": "check_fixture.py"},
        known_good=[],
        known_bad=["Wrong identifier"],
        open_issues=["Regression fails"],
        next_steps=["Reproduce and repair"],
        context_refs=[],
    )
    red = run_check(folder)
    assert red["exit_code"] != 0 and "AssertionError" in red["stderr"], red
    receipt(service, work_id, "role-a", "reproduce", red, "repair")
    fixture.write_text("def window_handle(row):\n    return row['hwnd']\n", encoding="utf-8")
    green = run_check(folder)
    assert green["exit_code"] == 0, green
    green["fixture_sha256"] = digest(fixture)
    green["test_sha256"] = digest(folder / "check_fixture.py")
    receipt(service, work_id, "role-a", "regression", green, "handoff")
    unit = service.get(work_id=work_id)
    service.checkpoint(
        work_id=work_id,
        actor_agent="role-a",
        expected_revision=unit["revision"],
        current_state={
            "fixture": "fixture.py",
            "test": "check_fixture.py",
            "fixture_sha256": green["fixture_sha256"],
            "test_sha256": green["test_sha256"],
        },
        next_steps=["Verify fixture hashes and rerun regression"],
        files_touched=["fixture.py"],
        tests=[green],
        open_issues=[],
    )
    service.handoff(
        work_id=work_id,
        from_agent="role-a",
        to_agent="role-b",
        summary="Synthetic regression repaired",
        next_action="Re-run recovered test",
    )
    return {
        "role": "role-a",
        "pid": os.getpid(),
        "red_exit": red["exit_code"],
        "green_exit": green["exit_code"],
    }


def verify_recovered(db: Path, work_id: str, agent: str) -> tuple[Store, WorkUnitService, dict]:
    store = Store(db)
    service = WorkUnitService(store)
    unit = service.resume(work_id=work_id, agent_id=agent)
    assert unit["owner_agent"] == agent
    state = unit["current_state"]
    assert state["fixture"] == "fixture.py" and state["test"] == "check_fixture.py"
    assert digest(db.parent / state["fixture"]) == state["fixture_sha256"]
    assert digest(db.parent / state["test"]) == state["test_sha256"]
    assert store.verify_work_unit(work_id)["valid"]
    proof = run_check(db.parent)
    assert proof["exit_code"] == 0, proof
    proof["fixture_sha256"] = state["fixture_sha256"]
    return store, service, proof


def role_b(db: Path, work_id: str) -> dict:
    _, service, proof = verify_recovered(db, work_id, "role-b")
    receipt(service, work_id, "role-b", "replay_regression", proof, "handoff")
    service.handoff(
        work_id=work_id,
        from_agent="role-b",
        to_agent="role-c",
        summary="Independent process reran fixture regression",
        next_action="Verify and close",
    )
    return {"role": "role-b", "pid": os.getpid(), "exit_code": proof["exit_code"]}


def role_c(db: Path, work_id: str) -> dict:
    store, service, proof = verify_recovered(db, work_id, "role-c")
    receipt(service, work_id, "role-c", "final_regression", proof, "complete")
    unit = service.get(work_id=work_id)
    service.complete(work_id=work_id, actor_agent="role-c", expected_revision=unit["revision"])
    chain = store.verify_work_unit(work_id)
    assert chain["valid"]
    return {
        "role": "role-c",
        "pid": os.getpid(),
        "exit_code": proof["exit_code"],
        "chain_valid": chain["valid"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["a", "b", "c"])
    parser.add_argument("--db", type=Path)
    parser.add_argument("--work-id")
    args = parser.parse_args()
    if args.role:
        if args.db is None or not args.work_id:
            parser.error("role requires --db and --work-id")
        functions = {"a": role_a, "b": role_b, "c": role_c}
        print(json.dumps(functions[args.role](args.db, args.work_id)))
        return
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "demo.db"
        roles = []
        for role in ("a", "b", "c"):
            child = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--role",
                    role,
                    "--db",
                    str(db),
                    "--work-id",
                    WORK_ID,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=45,
                check=True,
                env={**os.environ, "PYTHONUTF8": "1"},
            )
            roles.append(json.loads(child.stdout))
        store = Store(db)
        service = WorkUnitService(store)
        chain = store.verify_work_unit(WORK_ID)
        unit = service.resume(work_id=WORK_ID, agent_id="observer")
        assert len({r["pid"] for r in roles}) == 3
        assert chain["valid"] and unit["status"] == "completed"
        assert unit["evidence_receipt_count"] == 4
        assert roles[0]["red_exit"] != 0 and roles[0]["green_exit"] == 0
        print(
            json.dumps(
                {
                    "demo": "three_process_handoff",
                    "mode": "synthetic_roles_not_ai_models",
                    "work_id": WORK_ID,
                    "roles": roles,
                    "integrity_entries": chain["entry_count"],
                    "chain_valid": chain["valid"],
                    "evidence_receipts": unit["evidence_receipt_count"],
                    "work_unit_status": unit["status"],
                    "all_assertions_passed": True,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Run verification examples without Python -O")
    main()
