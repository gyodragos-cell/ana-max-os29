"""Additional deterministic tests of core operational contracts."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from os29.capability_truth import reconcile
from os29.diagnosis import _failure_lineage, diagnose_trace
from os29.models import TraceEvent
from os29.redaction import is_sensitive_key, redact_text, redact_value, sanitize_url
from os29.scope import ScopePolicy
from os29.store import Store
from os29.truth_decay import classify


def event(**kw):
    return TraceEvent(
        **(
            {
                "trace_id": "edge",
                "source": "test",
                "component": "unit",
                "kind": "diagnostic",
                "action": "verify",
            }
            | kw
        )
    )


@pytest.mark.parametrize(
    "kw,match",
    [
        ({"source": ""}, "source"),
        ({"action": "x" * 257}, "256"),
        ({"outcome": "invalid"}, "outcome"),
        ({"duration_ms": True}, "duration_ms"),
        ({"duration_ms": float("inf")}, "duration_ms"),
        ({"duration_ms": -1}, "duration_ms"),
        ({"parent_event_id": 1}, "parent_event_id"),
        ({"target": "x" * 4097}, "4096"),
        ({"timestamp": 1}, "timestamp"),
        ({"timestamp": "bad"}, "ISO-8601"),
        ({"attributes": []}, "attributes"),
        ({"schema_version": "v2"}, "unsupported"),
    ],
)
def test_trace_validation(kw, match):
    with pytest.raises(ValueError, match=match):
        event(**kw).to_dict()


def test_event_from_dict_rejections():
    with pytest.raises(ValueError, match="JSON object"):
        TraceEvent.from_dict([])
    with pytest.raises(ValueError, match="unknown event fields"):
        TraceEvent.from_dict({"extra": 1})
    value = event(duration_ms=0).to_dict()
    assert TraceEvent.from_dict(value).to_dict() == value


@pytest.mark.parametrize(
    "parents,depth,warning",
    [
        ({"a": "a"}, 128, "parent_cycle_detected"),
        ({"a": "missing"}, 128, "parent_event_not_in_trace"),
        ({"a": "b", "b": "c", "c": None}, 1, "lineage_depth_limit_reached"),
    ],
)
def test_failure_lineage_boundaries(parents, depth, warning):
    rows = {k: {"event_id": k, "parent_event_id": v} for k, v in parents.items()}
    result = _failure_lineage(rows["a"], rows, max_depth=depth)
    assert warning in result["warnings"]
    assert result["root_cause"] is None


def test_diagnosis_no_failure(tmp_path):
    store = Store(tmp_path / "diag.db")
    with pytest.raises(ValueError, match="trace not found"):
        diagnose_trace(store, "missing")
    store.record_event(event())
    result = diagnose_trace(store, "edge")
    assert result["failure_count"] == 0
    assert result["incident"] is None
    assert result["root_cause"] is None


def test_catalog_reconciliation():
    result = reconcile(
        [{"name": "live"}, "source", {}, None, ""],
        ["live", "backend"],
        ["live", "gateway"],
        ["live", "partial"],
    )
    statuses = {r["name"]: r["status"] for r in result["rows"]}
    assert statuses == {
        "live": "LIVE_CANDIDATE",
        "source": "SOURCE_ONLY",
        "backend": "BACKEND_ONLY",
        "gateway": "GATEWAY_ONLY",
        "partial": "PARTIAL_REACHABILITY",
    }
    assert result["side_effects"] == []


@pytest.mark.parametrize(
    "age,expected",
    [
        (-1, "LIVE_CURRENT"),
        (300, "LIVE_CURRENT"),
        (301, "FRESH"),
        (3601, "AGING"),
        (86401, "STALE"),
        (604801, "EXPIRED"),
    ],
)
def test_evidence_age_boundaries(age, expected):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert classify((now - timedelta(seconds=age)).isoformat(), now) == expected


@pytest.fixture
def scope(tmp_path):
    path = tmp_path / "scope.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "os29.scope.v1",
                "approved_hosts": ["localhost"],
                "approved_ports": [80, 11434],
                "approved_networks": ["127.0.0.0/8"],
                "approved_device_ids": ["test-device"],
                "approved_process_names": ["python.exe"],
            }
        ),
        encoding="utf-8",
    )
    return ScopePolicy(path)


@pytest.mark.parametrize(
    "target,reason",
    [
        ("ftp://localhost", "scheme_not_allowed"),
        ("http:///path", "missing_hostname"),
        ("http://user:pass@localhost", "embedded_credentials_forbidden"),
        ("http://localhost:99999", "invalid_port"),
        ("http://[broken", "invalid_target"),
        ("http://example.invalid", "host_not_in_scope"),
        ("http://localhost:81", "port_not_in_scope"),
    ],
)
def test_scope_refusals(scope, target, reason):
    assert scope.check_target(target)["reason"] == reason


def test_scope_local_network_and_identity(scope):
    assert scope.check_target("http://127.0.0.2")["allowed"]
    assert scope.check_device("")["reason"] == "missing_device_id"
    assert scope.check_device("other")["allowed"] is False
    assert scope.check_device("test-device")["allowed"]
    assert scope.check_process("")["reason"] == "missing_process_name"
    assert scope.check_process("other.exe")["allowed"] is False
    assert scope.check_process("PYTHON.EXE")["allowed"]


def test_scope_invalid_schema(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="unsupported scope"):
        ScopePolicy(p)


@pytest.mark.parametrize("value", ["http://[broken", "http://localhost:bad", "ftp://localhost"])
def test_bad_url_redaction(value):
    assert sanitize_url(value) == ("[INVALID_URL]", 1)


def test_safe_url_and_redaction_fallbacks():
    url, count = sanitize_url("https://user:pass@[::1]:8443/path?x=hello&token=fixture")
    assert url.startswith("https://[::1]:8443/path?")
    assert "fixture" not in url and "user:pass" not in url and count >= 1
    assert redact_text(123) == ("123", 0)
    assert redact_value(1 + 2j) == ("(1+2j)", 0)
    assert is_sensitive_key("myPrivateKey")
    assert redact_value(("plain", {"password": "fixture"})) == (
        ["plain", {"password": "[REDACTED]"}],
        1,
    )
