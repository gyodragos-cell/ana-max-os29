from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import re

ROOT = Path(__file__).resolve().parents[1]


class LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {"src", "href"} and value:
                self.links.append(value)


def test_release_preview_is_not_a_pages_deployment():
    text = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "actions/deploy-pages" not in text
    assert "pages: write" not in text
    assert "id-token: write" not in text
    assert "actions/upload-artifact@v4" in text


def test_site_uses_synthetic_diagrams_and_has_no_missing_local_assets():
    path = ROOT / "site/index.html"
    text = path.read_text(encoding="utf-8")
    assert "ILLUSTRATIVE DEMO" in text
    assert "not screenshots or live telemetry" in text
    assert not re.search(r"\b" + "PC" + "1313" + r"\b", text, re.I)
    parser = LocalLinks()
    parser.feed(text)
    for url in parser.links:
        parts = urlsplit(url)
        if not parts.scheme and not parts.netloc and parts.path:
            assert (path.parent / parts.path).is_file(), url


def test_release_has_no_unreviewed_binary_assets():
    assert not list((ROOT / "site/assets").glob("*.png"))
