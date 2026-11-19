from os29.watchtower import Watchtower, PersistentCheckpointService


def test_persistent_checkpoint_roundtrip(tmp_path):
    cp = {"task": "t", "result": "ok", "evidence": [], "risk": "low", "blockers": [], "next_action": "none", "rollback": "none"}
    s = PersistentCheckpointService(str(tmp_path / "cp.db"))
    assert s.save("p1", cp).status == "SAVED"
    assert s.save("p1", cp).status == "DUPLICATE"
    assert s.resume("p1").status == "RESUMABLE"
    assert s.rollback("p1").status == "ROLLBACK_POINT_AVAILABLE"
    assert s.resume("missing").status == "STALE_OR_MISSING"


def test_watchtower_contracts_are_available_and_nonexecuting():
    w = Watchtower()
    assert w.side_effects == []
    assert w.capability_truth.reconcile({"source": ["a"], "registry": ["a"], "gateway": ["a"], "bridge": ["a"]}).status == "RECONCILED_INPUTS"
    assert w.trace_lineage.validate({"event_id": "e", "trace_id": "t", "source": "pi", "component": "x", "kind": "k", "action": "a"}).status == "VALID"
    assert w.trace_lineage.validate({"parent_trace_id": "bad"}).status == "INVALID"
    assert w.anti_repeat.recommend({"task_id": "t", "agent": "pi", "workspace": "lab"}).status == "NEW_TASK"
    assert w.sentinel.observe({"services": [], "error_fingerprints": []}).status == "HEALTHY"
    checkpoint = {"task": "t", "result": "ok", "evidence": [], "risk": "low", "blockers": [], "next_action": "none", "rollback": "none"}
    assert w.checkpoints.inspect(checkpoint).status == "VALID"
    assert w.checkpoints.save("cp-1", checkpoint).status == "SAVED"
    assert w.checkpoints.save("cp-1", checkpoint).status == "DUPLICATE"
    assert w.checkpoints.resume("cp-1").status == "RESUMABLE"
    assert w.checkpoints.rollback("cp-1").status == "ROLLBACK_POINT_AVAILABLE"
    assert w.checkpoints.resume("missing").status == "STALE_OR_MISSING"
    assert w.observability.summarize({"running": ["ana"]}).status == "OBSERVED"
    assert w.evidence.register({"source": "test", "method": "fixture", "result": "ok", "evidence": "e1", "confidence": "high"}).status == "EVIDENCED"
    assert w.maturity.advance("sentinel", "VALIDATED", "INTEGRATED", {"source": "tests", "method": "pytest", "result": "17 passed", "evidence": "test_run"}).status == "ADVANCED"
    assert w.maturity.advance("sentinel", "VALIDATED", "SERVICE", {"source": "tests", "method": "pytest", "result": "17 passed", "evidence": "test_run"}).status == "BLOCKED"
