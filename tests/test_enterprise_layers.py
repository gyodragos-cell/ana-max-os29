from datetime import datetime, timezone, timedelta
from os29.contracts import make_attestation
from os29.conformance import certify
from os29.truth_decay import classify
from os29.watchtower import Watchtower


def test_attestation_integrates_with_registry():
    c = make_attestation("e1", "pytest", "fixture", "PASS", "high")
    c["evidence"] = "fixture"
    assert Watchtower().evidence.register(c).status == "VERIFIED"
    c["result"] = "tampered"
    assert Watchtower().evidence.register(c).status == "INVALID_HASH"


def test_conformance_classification():
    assert certify("OS29", {k: True for k in ("contracts", "evidence", "trace", "checkpoint", "gateway", "anti_repeat", "sentinel", "observability")})["status"] == "CERTIFIED"
    assert certify("new", {"contracts": True})["status"] == "LIMITED"


def test_truth_decay():
    now = datetime.now(timezone.utc)
    assert classify(now.isoformat(), now) == "LIVE_CURRENT"
    assert classify((now - timedelta(days=8)).isoformat(), now) == "EXPIRED"
