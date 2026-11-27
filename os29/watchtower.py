"""Watchtower Control Plane service contracts.

All services are bounded and side-effect free by default. They provide a common
contract for GPT, NEMO, ANA, Pokee and future agents without owning agent
credentials or executing repairs.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .anti_repeat import evaluate
from .capability_truth import reconcile
from .contracts import attest
from .sentinel import evaluate_snapshot

MATURITY_LEVELS = (
    "DESIGN",
    "VALIDATED",
    "INTEGRATED",
    "SERVICE",
    "RELEASE_CANDIDATE",
    "PRODUCTION_CANDIDATE",
    "PRODUCTION_READY",
)


@dataclass(frozen=True)
class ServiceResult:
    service: str
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class CapabilityTruthService:
    name = "CapabilityTruthService"

    def reconcile(self, catalogs: Mapping[str, Any]) -> ServiceResult:
        result = reconcile(
            catalogs.get("source", []),
            catalogs.get("registry", []),
            catalogs.get("gateway", []),
            catalogs.get("bridge", []),
        )
        return ServiceResult(
            self.name,
            result["status"],
            result,
            [{"method": "bounded_catalog_reconciliation", "confidence": "observed"}],
        )


class TraceLineageService:
    name = "TraceLineageService"

    def validate(self, event: Mapping[str, Any]) -> ServiceResult:
        if "parent_trace_id" in event:
            return ServiceResult(self.name, "INVALID", errors=["parent_trace_id_forbidden"])
        required = {"event_id", "trace_id", "source", "component", "kind", "action"}
        missing = sorted(required - set(event))
        if missing:
            return ServiceResult(self.name, "UNVERIFIED", errors=["missing:" + ",".join(missing)])
        return ServiceResult(
            self.name,
            "VALID",
            {
                "event_id": event["event_id"],
                "parent_event_id": event.get("parent_event_id", ""),
            },
            [{"method": "schema_validation", "confidence": "observed"}],
        )


class AntiRepeatService:
    name = "AntiRepeatService"

    def recommend(self, task: Mapping[str, Any]) -> ServiceResult:
        result = evaluate(task)
        return ServiceResult(
            self.name,
            result["status"],
            result,
            [{"method": "deterministic_task_evaluation", "confidence": "observed"}],
        )


class SentinelService:
    name = "SentinelService"

    def observe(self, snapshot: Mapping[str, Any]) -> ServiceResult:
        result = evaluate_snapshot(snapshot)
        return ServiceResult(
            self.name,
            result["status"],
            result,
            [{"method": "bounded_snapshot_analysis", "confidence": "observed"}],
        )


class CheckpointService:
    name = "CheckpointService"

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def inspect(self, checkpoint: Mapping[str, Any]) -> ServiceResult:
        required = {
            "task",
            "result",
            "evidence",
            "risk",
            "blockers",
            "next_action",
            "rollback",
        }
        missing = sorted(required - set(checkpoint))
        if missing:
            return ServiceResult(self.name, "UNVERIFIED", errors=["missing:" + ",".join(missing)])
        return ServiceResult(
            self.name,
            "VALID",
            dict(checkpoint),
            [{"method": "checkpoint_contract_validation", "confidence": "observed"}],
        )

    def save(self, checkpoint_id: str, checkpoint: Mapping[str, Any]) -> ServiceResult:
        checked = self.inspect(checkpoint)
        if checked.status != "VALID":
            return checked
        if checkpoint_id in self._records and self._records[checkpoint_id] == dict(checkpoint):
            return ServiceResult(
                self.name,
                "DUPLICATE",
                {"checkpoint_id": checkpoint_id},
                [{"method": "deterministic_duplicate_check", "confidence": "observed"}],
            )
        self._records[checkpoint_id] = dict(checkpoint)
        return ServiceResult(
            self.name,
            "SAVED",
            {"checkpoint_id": checkpoint_id, "checkpoint": dict(checkpoint)},
            [{"method": "bounded_memory_save", "confidence": "observed"}],
        )

    def resume(self, checkpoint_id: str) -> ServiceResult:
        if checkpoint_id not in self._records:
            return ServiceResult(
                self.name,
                "STALE_OR_MISSING",
                {"checkpoint_id": checkpoint_id},
                errors=["checkpoint_not_found"],
            )
        return ServiceResult(
            self.name,
            "RESUMABLE",
            {
                "checkpoint_id": checkpoint_id,
                "checkpoint": dict(self._records[checkpoint_id]),
            },
            [{"method": "bounded_memory_resume", "confidence": "observed"}],
        )

    def rollback(self, checkpoint_id: str) -> ServiceResult:
        if checkpoint_id not in self._records:
            return ServiceResult(
                self.name,
                "UNVERIFIED",
                {"checkpoint_id": checkpoint_id},
                errors=["rollback_point_not_found"],
            )
        return ServiceResult(
            self.name,
            "ROLLBACK_POINT_AVAILABLE",
            {
                "checkpoint_id": checkpoint_id,
                "checkpoint": dict(self._records[checkpoint_id]),
            },
            [{"method": "bounded_memory_rollback_lookup", "confidence": "observed"}],
        )


class PersistentCheckpointService(CheckpointService):
    """SQLite-backed checkpoint contract; caller supplies an isolated DB path."""

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS watchtower_checkpoints (checkpoint_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def save(self, checkpoint_id: str, checkpoint: Mapping[str, Any]) -> ServiceResult:
        checked = self.inspect(checkpoint)
        if checked.status != "VALID":
            return checked
        payload = json.dumps(dict(checkpoint), sort_keys=True)
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT payload FROM watchtower_checkpoints WHERE checkpoint_id=?",
                (checkpoint_id,),
            ).fetchone()
            if row and row[0] == payload:
                return ServiceResult(self.name, "DUPLICATE", {"checkpoint_id": checkpoint_id})
            db.execute(
                "INSERT OR REPLACE INTO watchtower_checkpoints VALUES (?,?)",
                (checkpoint_id, payload),
            )
        return ServiceResult(self.name, "SAVED", {"checkpoint_id": checkpoint_id})

    def resume(self, checkpoint_id: str) -> ServiceResult:
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT payload FROM watchtower_checkpoints WHERE checkpoint_id=?",
                (checkpoint_id,),
            ).fetchone()
        if not row:
            return ServiceResult(self.name, "STALE_OR_MISSING", {"checkpoint_id": checkpoint_id})
        return ServiceResult(
            self.name,
            "RESUMABLE",
            {"checkpoint_id": checkpoint_id, "checkpoint": json.loads(row[0])},
        )

    def rollback(self, checkpoint_id: str) -> ServiceResult:
        result = self.resume(checkpoint_id)
        if result.status == "RESUMABLE":
            return ServiceResult(
                self.name,
                "ROLLBACK_POINT_AVAILABLE",
                result.data,
                result.evidence,
                result.errors,
            )
        return result


class ObservabilityService:
    name = "ObservabilityService"

    def summarize(self, snapshot: Mapping[str, Any]) -> ServiceResult:
        return ServiceResult(
            self.name,
            "OBSERVED",
            {
                "running": snapshot.get("running", []),
                "blocked": snapshot.get("blocked", []),
                "degraded": snapshot.get("degraded", []),
                "orphaned": snapshot.get("orphaned", []),
                "experimental": snapshot.get("experimental", []),
                "production_candidate": snapshot.get("production_candidate", []),
            },
            [{"method": "bounded_operational_snapshot", "confidence": "observed"}],
        )


class EvidenceRegistryService:
    name = "EvidenceRegistryService"

    def register(self, claim: Mapping[str, Any]) -> ServiceResult:
        required = {"source", "method", "result", "evidence", "confidence"}
        missing = sorted(required - set(claim))
        if missing:
            return ServiceResult(
                self.name,
                "UNVERIFIED",
                {"claim_status": "UNVERIFIED"},
                errors=["missing:" + ",".join(missing)],
            )
        if "evidence_id" in claim:
            attestation = attest(claim)
            return ServiceResult(
                self.name,
                attestation["status"],
                {"claim_status": attestation["status"], **dict(claim)},
                [
                    {
                        "method": str(claim["method"]),
                        "confidence": str(claim["confidence"]),
                    }
                ],
                attestation.get("missing", []),
            )
        return ServiceResult(
            self.name,
            "EVIDENCED",
            {"claim_status": "VERIFIED", **dict(claim)},
            [{"method": str(claim["method"]), "confidence": str(claim["confidence"])}],
        )


class MaturityService:
    name = "MaturityService"

    def advance(
        self, component: str, current: str, target: str, evidence: Mapping[str, Any]
    ) -> ServiceResult:
        if current not in MATURITY_LEVELS or target not in MATURITY_LEVELS:
            return ServiceResult(self.name, "INVALID", errors=["unknown_maturity"])
        if MATURITY_LEVELS.index(target) != MATURITY_LEVELS.index(current) + 1:
            return ServiceResult(self.name, "BLOCKED", errors=["non_sequential_transition"])
        if not all(evidence.get(k) for k in ("source", "method", "result", "evidence")):
            return ServiceResult(self.name, "UNVERIFIED", errors=["insufficient_evidence"])
        return ServiceResult(
            self.name,
            "ADVANCED",
            {"component": component, "from": current, "to": target},
            [
                {
                    "method": str(evidence["method"]),
                    "confidence": str(evidence.get("confidence", "observed")),
                }
            ],
        )


class Watchtower:
    """Facade exposing all contracts; no execution or persistence is performed."""

    def __init__(self) -> None:
        self.capability_truth = CapabilityTruthService()
        self.trace_lineage = TraceLineageService()
        self.anti_repeat = AntiRepeatService()
        self.sentinel = SentinelService()
        self.checkpoints = CheckpointService()
        self.observability = ObservabilityService()
        self.evidence = EvidenceRegistryService()
        self.maturity = MaturityService()

    @property
    def side_effects(self) -> list[str]:
        return []
