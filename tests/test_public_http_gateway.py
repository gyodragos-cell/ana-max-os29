"""Public HTTP gateway integration tests on an ephemeral loopback port."""

from __future__ import annotations

import http.client
import json
import threading

import pytest

from os29.gateway import MAX_BODY_BYTES, make_server
from os29.models import TraceEvent

TEST_TOKEN = "fixture-" + "x" * 32


@pytest.fixture
def gateway(tmp_path):
    server = make_server(tmp_path / "gateway.db", TEST_TOKEN, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def request(port, method, path, data=None, authorized=True, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    request_headers = dict(headers or {})
    if authorized:
        request_headers["Authorization"] = "Bearer " + TEST_TOKEN
    body = json.dumps(data).encode("utf-8") if isinstance(data, (dict, list)) else data
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_gateway_health_auth_and_read_routes(gateway):
    assert request(gateway, "GET", "/health", authorized=False)[0] == 200
    assert request(gateway, "GET", "/status", authorized=False)[0] == 401
    assert request(gateway, "POST", "/events", {}, authorized=False)[0] == 401
    for path in ("/status", "/capabilities", "/capability-edges", "/traces/empty"):
        assert request(gateway, "GET", path)[0] == 200
    assert request(gateway, "GET", "/capsules/missing")[0] == 404
    assert request(gateway, "GET", "/not-found")[0] == 404


def test_gateway_real_persistence_and_validation(gateway):
    event = TraceEvent(
        trace_id="public-gateway-trace",
        source="test",
        component="gateway",
        kind="test.observation",
        action="synthetic",
        outcome="observed",
    ).to_dict()
    code, payload = request(gateway, "POST", "/events", event)
    assert code == 201 and payload["event_id"] == event["event_id"]
    code, payload = request(gateway, "GET", "/traces/public-gateway-trace")
    assert code == 200 and payload["events"][0]["event_id"] == event["event_id"]
    assert request(gateway, "POST", "/events", {"unknown": True})[0] == 400
    assert request(gateway, "POST", "/capsules", {"mission_id": "capsule"})[0] == 400
    capsule = {
        "project": "public-test",
        "objective": "verify",
        "current_state": {},
        "known_good": [],
        "known_bad": [],
        "open_issues": [],
        "next_steps": ["test"],
    }
    assert (
        request(
            gateway, "POST", "/capsules", {"mission_id": "capsule", "capsule": capsule}
        )[0]
        == 201
    )
    assert (
        request(gateway, "GET", "/capsules/capsule")[1]["capsule"]["project"]
        == "public-test"
    )
    capability = {"kind": "service", "name": "fixture", "status": "running"}
    assert request(gateway, "POST", "/capabilities", capability)[0] == 201
    assert (
        request(gateway, "GET", "/capabilities")[1]["capabilities"][0]["name"]
        == "fixture"
    )
    assert request(gateway, "POST", "/not-found", {})[0] == 404


def test_gateway_payload_bounds(gateway):
    assert request(gateway, "POST", "/events", b"{")[0] == 400
    assert request(gateway, "POST", "/events", b"\xff")[0] == 400
    assert request(gateway, "POST", "/events", [1])[0] == 400
    assert (
        request(
            gateway,
            "POST",
            "/events",
            b"",
            headers={"Content-Length": str(MAX_BODY_BYTES + 1)},
        )[0]
        == 413
    )
    assert (
        request(gateway, "POST", "/events", b"", headers={"Content-Length": "bad"})[0]
        == 411
    )


def test_gateway_rejects_non_loopback_and_short_credentials(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        make_server(tmp_path / "unused.db", TEST_TOKEN, host="0.0.0.0")
    with pytest.raises(ValueError, match="32 characters"):
        make_server(tmp_path / "unused.db", "short", port=0)
