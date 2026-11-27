from __future__ import annotations

import json
from pathlib import Path

from os29 import cli, mcp_stdio
from os29.scope import ScopePolicy

ROOT = Path(__file__).resolve().parents[1]


def test_default_scope_is_inside_installable_package():
    package = Path(cli.__file__).resolve().parent
    bundled = package / "lab_scope.json"
    assert bundled.is_file()
    assert bundled == cli.DEFAULT_SCOPE
    assert bundled == mcp_stdio.SCOPE_PATH
    assert json.loads(bundled.read_text(encoding="utf-8")) == json.loads(
        (ROOT / "config/lab_scope.json").read_text(encoding="utf-8")
    )
    policy = ScopePolicy(bundled)
    assert policy.check_target("http://localhost:7777")["allowed"] is True
    assert policy.check_target("http://localhost:8080")["allowed"] is False
    assert policy.check_target("https://example.com")["allowed"] is False
