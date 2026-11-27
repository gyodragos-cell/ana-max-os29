from __future__ import annotations

import json
from pathlib import Path

from integrations.os28 import MockOS28Provider, ToolDescriptor


def test_os28_mock_is_deterministic_and_offline():
    mock = MockOS28Provider()
    descriptor = mock.list_tools()[0]
    assert isinstance(descriptor, ToolDescriptor)
    assert descriptor.name == "example.echo"
    assert mock.call("example.echo", {"text": "hello"}) == {
        "text": "hello",
        "mock": True,
    }


def test_public_mcp_example_uses_placeholder_paths():
    root = Path(__file__).resolve().parents[1]
    data = json.loads(
        (root / "examples" / "mcp_client.example.json").read_text(encoding="utf-8")
    )
    assert data["mcpServers"]["os29-local"]["env"]["OS29_DB_PATH"].startswith(
        "<local-path>"
    )
