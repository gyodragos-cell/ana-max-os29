"""Read-only pre-crash sentinel decision model.

Consumes bounded snapshots and emits findings only. It never probes services,
starts processes, calls tools, writes state, or performs repairs.
"""
from __future__ import annotations

from typing import Any, Mapping


VALID_STATUSES = {"HEALTHY", "DEGRADED", "BLOCKED", "UNKNOWN"}


def evaluate_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        return {"status": "UNKNOWN", "findings": ["snapshot_must_be_object"], "repair_hints": []}
    findings: list[str] = []
    hints: list[str] = []
    services = snapshot.get("services", [])
    if not isinstance(services, list):
        findings.append("services_shape_invalid")
    else:
        for service in services:
            if not isinstance(service, Mapping):
                findings.append("service_entry_invalid")
                continue
            name = str(service.get("name") or "unknown")
            status = str(service.get("status") or "unknown")
            if status not in {"running", "online", "ok"}:
                findings.append(f"service_degraded:{name}:{status}")
                hints.append(f"inspect_service:{name}")
    errors = snapshot.get("error_fingerprints", [])
    if isinstance(errors, list):
        repeated = {str(e) for e in errors if e is not None}
        for error in sorted(repeated):
            if sum(1 for item in errors if str(item) == error) >= 2:
                findings.append(f"repeated_error:{error[:200]}")
                hints.append("operator_review_before_retry")
    else:
        findings.append("error_fingerprints_shape_invalid")
    if snapshot.get("catalog_drift") is True:
        findings.append("catalog_drift_detected")
        hints.append("capture_authenticated_catalog_artifact")
    if snapshot.get("dependency_blocker"):
        blocker = str(snapshot["dependency_blocker"])[:200]
        findings.append(f"dependency_blocked:{blocker}")
        hints.append("inspect_dependency_without_auto_install")
    status = "HEALTHY" if not findings else "DEGRADED"
    return {
        "status": status,
        "findings": findings,
        "repair_hints": sorted(set(hints)),
        "auto_action": False,
        "evidence_only": True,
    }
