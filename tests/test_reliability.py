from os29.reliability import recommend


def test_reliability_facade_is_recommendation_only():
    result = recommend(
        {"task_id": "t", "agent": "pi", "workspace": "lab"},
        {"services": [{"name": "ana", "status": "online"}], "error_fingerprints": []},
    )
    assert result["recommendation_only"] is True
    assert result["actions_executed"] == []
    assert result["planner"]["status"] == "NEW_TASK"
    assert result["sentinel"]["status"] == "HEALTHY"
    assert result["lineage_field"] == "parent_event_id"
