from os29.sentinel import evaluate_snapshot


def test_healthy_snapshot():
    result = evaluate_snapshot(
        {"services": [{"name": "ana", "status": "online"}], "error_fingerprints": []}
    )
    assert result["status"] == "HEALTHY"
    assert result["auto_action"] is False


def test_degraded_service_and_dependency():
    result = evaluate_snapshot(
        {
            "services": [{"name": "selenium", "status": "blocked"}],
            "error_fingerprints": ["E", "E"],
            "dependency_blocker": "driver",
        }
    )
    assert result["status"] == "DEGRADED"
    assert "operator_review_before_retry" in result["repair_hints"]
    assert result["auto_action"] is False


def test_catalog_drift_is_reported():
    result = evaluate_snapshot({"services": [], "error_fingerprints": [], "catalog_drift": True})
    assert "catalog_drift_detected" in result["findings"]
