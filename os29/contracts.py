"""Versioned Watchtower contract registry and evidence attestation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class Contract:
    name: str
    version: str
    owner: str
    schema: tuple[str, ...]
    evidence_rules: tuple[str, ...]
    deprecation_policy: str


CONTRACTS = {
    c.name: c
    for c in (
        Contract(
            "capability",
            "v1",
            "watchtower",
            ("name", "status", "evidence"),
            ("source", "method", "result"),
            "supersede-only",
        ),
        Contract(
            "trace",
            "v1",
            "watchtower",
            ("event_id", "parent_event_id"),
            ("event_id", "parent_event_id"),
            "supersede-only",
        ),
        Contract(
            "checkpoint",
            "v1",
            "watchtower",
            (
                "task",
                "result",
                "evidence",
                "risk",
                "blockers",
                "next_action",
                "rollback",
            ),
            ("source", "method", "result"),
            "supersede-only",
        ),
        Contract(
            "evidence",
            "v1",
            "watchtower",
            (
                "evidence_id",
                "source",
                "method",
                "timestamp",
                "result",
                "hash",
                "confidence",
            ),
            ("source", "method", "timestamp", "hash", "confidence"),
            "supersede-only",
        ),
        Contract(
            "sentinel",
            "v1",
            "watchtower",
            ("status", "findings", "evidence"),
            ("source", "method", "result"),
            "supersede-only",
        ),
        Contract(
            "antirepeat",
            "v1",
            "watchtower",
            ("task_id", "status", "reason"),
            ("source", "method", "result"),
            "supersede-only",
        ),
    )
}


def registry() -> dict[str, dict[str, Any]]:
    return {
        k: {
            "version": v.version,
            "owner": v.owner,
            "schema": list(v.schema),
            "evidence_rules": list(v.evidence_rules),
            "deprecation_policy": v.deprecation_policy,
        }
        for k, v in CONTRACTS.items()
    }


def attest(claim: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "evidence_id",
        "source",
        "method",
        "timestamp",
        "result",
        "hash",
        "confidence",
    )
    missing = [k for k in required if not claim.get(k)]
    if missing:
        return {"status": "UNVERIFIED", "missing": missing}
    payload = {k: claim[k] for k in required if k != "hash"}
    expected = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return {
        "status": "VERIFIED" if claim["hash"] == expected else "INVALID_HASH",
        "expected_hash": expected,
        "evidence_id": claim["evidence_id"],
    }


def make_attestation(
    evidence_id: str, source: str, method: str, result: Any, confidence: str
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).isoformat()
    payload = {
        "evidence_id": evidence_id,
        "source": source,
        "method": method,
        "timestamp": timestamp,
        "result": result,
        "confidence": confidence,
    }
    payload["hash"] = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload
