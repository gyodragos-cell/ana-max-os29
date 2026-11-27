from os29.anti_repeat import evaluate


def test_new_task():
    result = evaluate({"task_id": "t1", "agent": "pi", "workspace": "lab"})
    assert result["status"] == "NEW_TASK"
    assert result["duplicate_action_warning"] is False


def test_completed_is_not_repeated():
    result = evaluate(
        {
            "task_id": "t1",
            "agent": "pi",
            "workspace": "lab",
            "completed_actions": ["read"],
            "verified_evidence": ["e1"],
            "checkpoint_id": "c1",
            "next_action": "read",
        }
    )
    assert result["status"] == "ALREADY_VERIFIED"
    assert result["duplicate_action_warning"] is True


def test_resume_checkpoint():
    result = evaluate(
        {
            "task_id": "t1",
            "agent": "pi",
            "workspace": "lab",
            "checkpoint_id": "c1",
            "next_action": "verify",
        }
    )
    assert result["status"] == "RESUME_FROM_CHECKPOINT"


def test_repeated_error_blocks_retry():
    result = evaluate(
        {
            "task_id": "t1",
            "agent": "pi",
            "workspace": "lab",
            "error_fingerprints": ["E1", "E1"],
        }
    )
    assert result["status"] == "BLOCKED"
    assert result["duplicate_action_warning"] is True


def test_different_agent_workspace_is_independent():
    result = evaluate({"task_id": "t1", "agent": "nemo", "workspace": "other"})
    assert result["status"] == "NEW_TASK"


def test_invalid_lineage_is_rejected():
    result = evaluate(
        {"task_id": "t1", "agent": "pi", "workspace": "lab", "parent_trace_id": "bad"}
    )
    assert result["status"] == "REQUIRES_REVIEW"
    assert "parent_trace_id" in result["current_blocker"]
