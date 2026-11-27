import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "wait_pages_artifact", Path(__file__).resolve().parents[1] / "scripts/wait_pages_artifact.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NAME = "github-pages-123-2"
ARTIFACT = {"name": NAME, "id": 7, "size_in_bytes": 1234, "expired": False}


def test_waits_for_visibility_and_settles():
    responses = iter([[], [{"name": "different"}], [ARTIFACT]])
    sleeps = []
    result = module.wait_for_artifact(lambda: next(responses), NAME, attempts=3,
                                      delay=5, settle=10, sleep=sleeps.append)
    assert result == ARTIFACT
    assert sleeps == [5, 5, 10]


def test_duplicate_artifacts_fail_closed():
    with pytest.raises(RuntimeError, match="Multiple"):
        module.wait_for_artifact(lambda: [ARTIFACT, dict(ARTIFACT, id=8)], NAME,
                                 sleep=lambda _: None)


def test_missing_artifacts_have_bounded_wait():
    sleeps = []
    with pytest.raises(TimeoutError):
        module.wait_for_artifact(lambda: [], NAME, attempts=3, sleep=sleeps.append)
    assert sleeps == [5, 5]


def test_expired_artifact_is_not_used():
    with pytest.raises(TimeoutError):
        module.wait_for_artifact(lambda: [dict(ARTIFACT, expired=True)], NAME,
                                 attempts=1, sleep=lambda _: None)


def test_invalid_artifact_metadata_is_rejected():
    with pytest.raises(RuntimeError, match="invalid metadata"):
        module.wait_for_artifact(lambda: [dict(ARTIFACT, size_in_bytes=0)], NAME,
                                 sleep=lambda _: None)


def test_workflow_waits_between_upload_and_deploy():
    text = (Path(__file__).resolve().parents[1] / ".github/workflows/static.yml").read_text()
    assert "actions: read" in text
    assert text.index("actions/upload-pages-artifact") < text.index("scripts/wait_pages_artifact.py") < text.index("actions/deploy-pages")
