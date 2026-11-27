from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_pages_artifact_is_unique_per_attempt_and_matches_deploy():
    content = (ROOT / ".github/workflows/static.yml").read_text(encoding="utf-8")
    upload = re.search(r"uses: actions/upload-pages-artifact@v3\s+with:\s+path: [^\n]+\s+name: ([^\n]+)", content)
    deploy = re.search(r"uses: actions/deploy-pages@v4\s+with:\s+artifact_name: ([^\n]+)", content)
    assert upload and deploy
    assert upload.group(1) == deploy.group(1)
    assert "${{ github.run_id }}" in upload.group(1)
    assert "${{ github.run_attempt }}" in upload.group(1)
    assert "if: github.ref == 'refs/heads/main'" in content
