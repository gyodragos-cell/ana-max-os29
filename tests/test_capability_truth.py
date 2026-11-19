from os29.capability_truth import reconcile


def test_reconcile_classifies_sets_without_discovery():
    result = reconcile(["a", "b"], ["a", "b", "c"], ["a", "c"], ["a"])
    assert result["status"] == "RECONCILED_INPUTS"
    assert result["unverified"] is True
    rows = {row["name"]: row for row in result["rows"]}
    assert rows["a"]["status"] == "LIVE_CANDIDATE"
    assert rows["b"]["status"] == "BACKEND_ONLY"
    assert rows["c"]["status"] == "GATEWAY_ONLY"
    assert result["side_effects"] == []
