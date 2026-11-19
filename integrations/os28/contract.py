"""Portable OS28 adapter contract, not a running server or agent."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolProvider(Protocol):
    def list_tools(self) -> list[ToolDescriptor]: ...
    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class MockOS28Provider:
    """Pure in-process mock; performs no network or file operations."""

    def list_tools(self) -> list[ToolDescriptor]:
        return [ToolDescriptor(
            name="example.echo",
            description="Return an input string unchanged",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        )]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != "example.echo":
            raise ValueError("Unknown mock tool: " + name)
        value = arguments.get("text")
        if not isinstance(value, str):
            raise ValueError("text must be a string")
        return {"text": value, "mock": True}
