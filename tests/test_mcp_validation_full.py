# FILE: tests/test_mcp_validation_full.py
import io
import json

import pytest

from os29.mcp_stdio import encode_response, handle
from os29.mcp_validation import (
    MAX_FRAME_BYTES,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    iter_frames,
    parse_message,
    validate_json,
    validate_tool_arguments,
)


@pytest.mark.parametrize("identifier", [1, "abc", None])
def test_valid_request(identifier):
    request = {
        "jsonrpc": "2.0",
        "method": "ping",
        "params": {},
        "id": identifier,
        "extra": "permitted",
    }
    assert parse_message(json.dumps(request).encode()) == request
    assert handle(request) == {"jsonrpc": "2.0", "id": identifier, "result": {}}


@pytest.mark.parametrize(
    "patch,missing,code",
    [
        ({}, "jsonrpc", -32600),
        ({"jsonrpc": "1.0"}, None, -32600),
        ({}, "method", -32600),
        ({"method": 1}, None, -32600),
        ({"method": ""}, None, -32600),
        ({"params": []}, None, -32602),
        ({"params": 1}, None, -32602),
        ({"params": None}, None, -32602),
        ({"id": True}, None, -32600),
        ({"id": "x" * 257}, None, -32600),
    ],
)
def test_invalid_envelope(patch, missing, code):
    request = {"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1, **patch}
    if missing:
        del request[missing]
    assert handle(request)["error"]["code"] == code


def test_notification_and_unknown_method():
    assert handle({"jsonrpc": "2.0", "method": "ping"}) is None
    response = handle({"jsonrpc": "2.0", "method": "not_registered", "id": 1})
    assert response["error"]["code"] == -32601


@pytest.mark.parametrize(
    "response",
    [
        {"jsonrpc": "2.0", "result": {}, "id": 1},
        {"jsonrpc": "2.0", "error": {"code": -32600, "message": "err"}, "id": 1},
    ],
)
def test_response_roundtrip(response):
    assert parse_message(encode_response(response).encode("ascii")) == response


@pytest.mark.parametrize(
    "frame",
    [
        b'{"x":1,"x":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        b'{"x":1e999}',
        b"\xff",
        b"{",
        b"x" * (MAX_FRAME_BYTES + 1),
    ],
    ids=["duplicate", "nan", "inf", "negative-inf", "overflow", "utf8", "syntax", "oversized"],
)
def test_bad_frames(frame):
    with pytest.raises(ValueError) as error:
        parse_message(frame)
    assert str(error.value)


def test_frame_drain_and_recovery():
    stream = io.BytesIO(
        b"\n{}\n" + b"x" * (MAX_FRAME_BYTES * 2 + 3) + b"\n[]\n" + b"x" * (MAX_FRAME_BYTES + 1)
    )
    assert list(iter_frames(stream)) == [b"{}\n", None, b"[]\n", None]


@pytest.mark.parametrize(
    "value",
    [
        {1: "bad"},
        (1, 2),
        float("nan"),
        float("inf"),
        pytest.param([0] * MAX_JSON_NODES, id="max_nodes_list"),
        pytest.param({str(i): 0 for i in range(MAX_JSON_NODES)}, id="max_nodes_dict"),
    ],
)
def test_json_limits(value):
    with pytest.raises(ValueError) as error:
        validate_json(value)
    assert str(error.value)


def test_depth_limit():
    value = 0
    for _ in range(MAX_JSON_DEPTH + 1):
        value = [value]
    with pytest.raises(ValueError, match="structural limit") as error:
        validate_json(value)
    assert str(error.value) == "JSON structural limit exceeded"


@pytest.mark.parametrize(
    "schema,value",
    [
        ({"type": "object"}, []),
        ({"type": "object", "required": ["x"]}, {}),
        ({"type": "object", "additionalProperties": False}, {"x": 1}),
        ({"type": "array"}, {}),
        ({"type": "array", "minItems": 1}, []),
        ({"type": "array", "maxItems": 1}, [1, 2]),
        ({"type": "array", "items": {"type": "integer"}}, [True]),
        ({"type": "string"}, 1),
        ({"type": "string", "minLength": 2}, "a"),
        ({"type": "string", "maxLength": 1}, "ab"),
        ({"type": "integer"}, 1.5),
        ({"type": "number"}, True),
        ({"type": "number", "minimum": 0}, -1),
        ({"type": "number", "maximum": 1}, 2),
        ({"type": "boolean"}, 1),
        ({"type": "unsupported"}, 1),
        ({"enum": ["yes"]}, "no"),
    ],
)
def test_schema_rejections(schema, value):
    with pytest.raises(ValueError) as error:
        validate_tool_arguments(
            "test", {"x": value}, {"type": "object", "properties": {"x": schema}}
        )
    assert str(error.value)


def test_valid_nested_schema():
    schema = {
        "type": "object",
        "required": ["x"],
        "properties": {
            "x": {"type": "array", "items": {"type": "number"}},
            "flag": {"type": "boolean"},
            "name": {"type": "string", "enum": ["yes"]},
        },
    }
    assert (
        validate_tool_arguments("test", {"x": [1, 2.5], "flag": True, "name": "yes"}, schema)
        is None
    )


def test_top_level_extra_and_payload_limits():
    with pytest.raises(ValueError, match="unsupported test arguments") as extra:
        validate_tool_arguments("test", {"extra": 1}, {"additionalProperties": False})
    assert "extra" in str(extra.value)
    with pytest.raises(ValueError, match="payload limit") as large:
        validate_tool_arguments("test", {"x": "x" * MAX_FRAME_BYTES}, {})
    assert "payload limit" in str(large.value)
