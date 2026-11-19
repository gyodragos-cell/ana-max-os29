from os29.contracts import attest, make_attestation, registry


def test_contract_registry_is_versioned():
    r = registry()
    assert {"capability", "trace", "checkpoint", "evidence", "sentinel", "antirepeat"} <= set(r)
    assert all(v["version"] == "v1" for v in r.values())


def test_evidence_attestation_is_hash_verified():
    claim = make_attestation("e1", "pytest", "fixture", "PASS", "high")
    assert attest(claim)["status"] == "VERIFIED"
    claim["result"] = "TAMPERED"
    assert attest(claim)["status"] == "INVALID_HASH"


def test_missing_evidence_is_unverified():
    assert attest({"source": "x"})["status"] == "UNVERIFIED"
