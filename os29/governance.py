"""Deterministic enterprise governance registries for Watchtower."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceGraph:
    edges: list[dict[str, str]] = field(default_factory=list)

    def link(
        self,
        evidence_id: str,
        artifact_id: str,
        checkpoint_id: str,
        gate_id: str,
        decision_id: str,
    ) -> dict[str, Any]:
        edge = locals().copy()
        edge.pop("self")
        self.edges.append(edge)
        return {"status": "LINKED", **edge}

    def explain(self, gate_id: str) -> dict[str, Any]:
        matches = [e for e in self.edges if e["gate_id"] == gate_id]
        return {
            "status": "EVIDENCED" if matches else "UNVERIFIED",
            "gate_id": gate_id,
            "evidence": matches,
        }


@dataclass
class IncidentEngine:
    incidents: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(self, incident_id: str, **fields: Any) -> dict[str, Any]:
        required = (
            "root_cause",
            "evidence",
            "impact",
            "resolution",
            "rollback",
            "prevention",
        )
        missing = [k for k in required if not fields.get(k)]
        if missing:
            return {
                "status": "UNVERIFIED",
                "incident_id": incident_id,
                "missing": missing,
            }
        self.incidents[incident_id] = {
            "incident_id": incident_id,
            **{k: fields[k] for k in required},
        }
        return {"status": "RECORDED", **self.incidents[incident_id]}

    def postmortem(self, incident_id: str) -> dict[str, Any]:
        if incident_id not in self.incidents:
            return {"status": "UNVERIFIED", "incident_id": incident_id}
        return {"status": "POSTMORTEM_READY", **self.incidents[incident_id]}


@dataclass
class CertificationRegistry:
    records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def register(
        self, agent: str, classification: str, evidence: Mapping[str, Any]
    ) -> dict[str, Any]:
        if classification not in {
            "CERTIFIED",
            "LIMITED",
            "REJECTED",
        } or not evidence.get("source"):
            return {"status": "UNVERIFIED", "agent": agent}
        self.records[agent] = {
            "agent": agent,
            "classification": classification,
            "evidence": dict(evidence),
        }
        return {"status": "REGISTERED", **self.records[agent]}


@dataclass
class TrustRegistry:
    records: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(
        self,
        agent: str,
        verified_claims: int,
        failed_claims: int,
        rollback_incidents: int,
    ) -> dict[str, Any]:
        data = {
            "agent": agent,
            "verified_claims": verified_claims,
            "failed_claims": failed_claims,
            "rollback_incidents": rollback_incidents,
        }
        self.records[agent] = data
        return {"status": "RECORDED", **data}


@dataclass
class GovernanceRegistry:
    ownership: dict[str, str] = field(default_factory=dict)

    def assign(self, capability: str, owner: str) -> dict[str, Any]:
        if capability in self.ownership and self.ownership[capability] != owner:
            return {
                "status": "CONFLICT",
                "capability": capability,
                "existing_owner": self.ownership[capability],
            }
        self.ownership[capability] = owner
        return {"status": "ASSIGNED", "capability": capability, "owner": owner}


@dataclass
class OrganizationalMemory:
    records: list[dict[str, Any]] = field(default_factory=list)

    def remember(
        self,
        problem: str,
        cause: str,
        solution: str,
        evidence: str,
        rollback: str,
        incident: str,
    ) -> dict[str, Any]:
        record = locals().copy()
        record.pop("self")
        self.records.append(record)
        return {"status": "STORED", "record": record}
