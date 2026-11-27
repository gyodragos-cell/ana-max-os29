import json

from os29.anti_repeat_adapter import evaluate_json_file, evaluate_record


def test_record_adapter_is_read_only_contract():
    result = evaluate_record({"task_id": "t", "agent": "pi", "workspace": "lab"})
    assert result["status"] == "NEW_TASK"


def test_json_fixture_adapter(tmp_path):
    fixture = tmp_path / "task.json"
    fixture.write_text(
        json.dumps({"task_id": "t", "agent": "pi", "workspace": "lab"}),
        encoding="utf-8",
    )
    assert evaluate_json_file(fixture)["status"] == "NEW_TASK"


def test_missing_fixture_is_review():
    result = evaluate_json_file("does-not-exist.json")
    assert result["status"] == "REQUIRES_REVIEW"


def test_invalid_fixture_is_review(tmp_path):
    fixture = tmp_path / "bad.json"
    fixture.write_text("not json", encoding="utf-8")
    assert evaluate_json_file(fixture)["status"] == "REQUIRES_REVIEW"
