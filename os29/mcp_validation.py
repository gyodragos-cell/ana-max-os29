"""Bounded JSON-RPC framing and validation for the public STDIO provider."""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from typing import Any, BinaryIO

MAX_FRAME_BYTES = 1_048_576
MAX_OUTPUT_BYTES = 1_048_576
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 50_000


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate JSON object key")
        result[name] = value
    return result


def validate_json(value: Any) -> None:
    """Validate resource and finite-JSON bounds without recursive traversal."""
    stack = [(value, 0)]
    seen = 0
    while stack:
        item, depth = stack.pop()
        seen += 1
        if depth > MAX_JSON_DEPTH or seen > MAX_JSON_NODES:
            raise ValueError("JSON structural limit exceeded")
        if isinstance(item, dict):
            if len(item) > MAX_JSON_NODES - seen - len(stack):
                raise ValueError("JSON structural limit exceeded")
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            if len(item) > MAX_JSON_NODES - seen - len(stack):
                raise ValueError("JSON structural limit exceeded")
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("JSON numbers must be finite")
        elif type(item) not in {str, int, float, bool, type(None)}:
            raise ValueError("unsupported JSON value")


def parse_message(frame: bytes) -> Any:
    if len(frame) > MAX_FRAME_BYTES:
        raise ValueError("frame too large")
    value = json.loads(
        frame.decode("utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_pairs,
    )
    validate_json(value)
    return value


def iter_frames(stream: BinaryIO) -> Iterator[bytes | None]:
    """None represents one rejected oversized line, drained in bounded chunks."""
    while True:
        chunk = stream.readline(MAX_FRAME_BYTES + 1)
        if not chunk:
            return
        if len(chunk) <= MAX_FRAME_BYTES:
            if chunk.strip():
                yield chunk
            continue
        while not chunk.endswith(b"\n"):
            chunk = stream.readline(MAX_FRAME_BYTES + 1)
            if not chunk:
                break
        yield None


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", [])) - set(value))
        if missing:
            raise ValueError(f"{path} missing required fields: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise ValueError(f"{path} unsupported fields: {', '.join(extra)}")
        for key, child in value.items():
            if key in properties:
                _validate(child, properties[key], f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get(
            "maxItems", MAX_JSON_NODES
        ):
            raise ValueError(f"{path} array size outside schema")
        if "items" in schema:
            for i, child in enumerate(value):
                _validate(child, schema["items"], f"{path}[{i}]")
    elif kind == "string":
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
            "maxLength", MAX_FRAME_BYTES
        ):
            raise ValueError(f"{path} string length outside schema")
    elif kind in {"integer", "number"}:
        valid = type(value) is int if kind == "integer" else type(value) in {int, float}
        if not valid:
            raise ValueError(f"{path} must be a finite {kind}")
        if value < schema.get("minimum", -math.inf) or value > schema.get(
            "maximum", math.inf
        ):
            raise ValueError(f"{path} number outside schema")
    elif kind == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{path} must be a boolean")
    elif kind is not None:
        raise ValueError("unsupported schema type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} value outside schema enum")


def validate_tool_arguments(
    name: str, args: dict[str, Any], schema: dict[str, Any]
) -> None:
    validate_json(args)
    if (
        len(json.dumps(args, ensure_ascii=True, allow_nan=False).encode("ascii"))
        > MAX_FRAME_BYTES
    ):
        raise ValueError("tool arguments exceed payload limit")
    if schema.get("additionalProperties") is False:
        extra = sorted(set(args) - set(schema.get("properties", {})))
        if extra:
            raise ValueError(f"unsupported {name} arguments: {', '.join(extra)}")
    _validate(args, schema, "arguments")
