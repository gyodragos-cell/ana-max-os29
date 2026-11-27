"""Check the static release preview with real Chromium, not mocked DOM."""
from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1] / "site"


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            response = page.goto(f"http://127.0.0.1:{server.server_port}/")
            assert response is not None and response.status == 200
            for width in (320, 375, 390, 768, 1280, 1920):
                page.set_viewport_size({"width": width, "height": 800})
                dims = page.evaluate("({w:document.documentElement.clientWidth,s:document.documentElement.scrollWidth})")
                assert dims["s"] <= dims["w"] + 1, (width, dims)
            page.set_viewport_size({"width": 1280, "height": 800})
            page.locator("#inspector .tab-btn").last.click()
            assert json.loads(page.locator("#inspector-out").inner_text())["verify_result"]["valid"] is False
            page.locator("#inspector .tab-btn").first.click()
            assert json.loads(page.locator("#inspector-out").inner_text())["verify_result"]["valid"] is True
            page.locator("#copy-install").click()
            page.wait_for_function("document.getElementById('copy-status').textContent === 'Copied'")
            assert page.evaluate("navigator.clipboard.readText()") == 'python -m pip install -e ".[test]"'
            assert not errors, errors
            browser.close()
        print("RELEASE_BROWSER_PASS widths=6 inspector=2 clipboard=1 js_errors=0")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Run without Python -O")
    main()
