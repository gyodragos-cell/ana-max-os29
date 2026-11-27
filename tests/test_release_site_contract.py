from __future__ import annotations

import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class SiteLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.links.append(value)
            if key == "id" and value:
                self.ids.add(value)


def test_release_site_local_links_and_assets():
    path = ROOT / "site/index.html"
    content = path.read_text(encoding="utf-8")
    parser = SiteLinks()
    parser.feed(content)
    for link in parser.links:
        url = urlsplit(link)
        if not url.scheme and not url.netloc:
            if url.path:
                assert (path.parent / unquote(url.path)).is_file(), link
            elif url.fragment:
                assert url.fragment in parser.ids, link
    for link in re.findall(r"url\(['\"]?([^)'\"]+)['\"]?\)", content):
        url = urlsplit(link)
        if not url.scheme and not url.netloc:
            assert (path.parent / url.path).is_file(), link
    assert "DEMO SIMULATION" in content


def test_release_preview_does_not_deploy():
    workflow = (ROOT / ".github/workflows/pages.yml").read_text()
    assert "actions/deploy-pages" not in workflow
    assert "pages: write" not in workflow
    assert "id-token: write" not in workflow
    assert "actions/upload-artifact" in workflow


def test_readme_local_links():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        url = urlsplit(target)
        if not url.scheme and not url.netloc and url.path:
            assert (ROOT / unquote(url.path)).is_file(), target


def test_demo_uses_real_subprocess_regression_and_reports_simulation():
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples/05_multiagent_handoff_demo.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["mode"] == "synthetic_roles_not_ai_models"
    assert len({r["pid"] for r in data["roles"]}) == 3
    assert data["roles"][0]["red_exit"] != 0
    assert data["roles"][0]["green_exit"] == 0
    assert all(r["exit_code"] == 0 for r in data["roles"][1:])
    assert data["chain_valid"] and data["all_assertions_passed"]
    assert data["evidence_receipts"] == 4
