"""Pure, non-executing anti-repeat planner for OS28/OS29.

This module only classifies a bounded task record and returns a recommendation.
It does not call tools, access the network, mutate the filesystem/database, or
manage processes. Lineage uses parent_event_id only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

ALLOWED_STATUSES = frozenset(
    {
        "NEW_TASK",
        "RESUME_FROM_CHECKPOINT",
        "ALREADY_VERIFIED",
        "DUPLICATE_ACTION_WARNING",
        "BLOCKED",
        "REQUIRES_REVIEW",
        "READY_FOR_NEXT_STEP",
    }
)


@dataclass(frozen=True)
class PlannerInput:
    task_id: str
    agent: str
    workspace: str
    completed_actions: tuple[str, ...] = ()
    verified_evidence: tuple[str, ...] = ()
    checkpoint_id: str = ""
    blocker: str = ""
    error_fingerprints: tuple[str, ...] = ()
    rollback_point: str = ""
    next_action: str = ""
    parent_event_id: str = ""


@dataclass(frozen=True)
class PlannerOutput:
    task_id: str
    agent: str
    workspace: str
    completed_actions: list[str] = field(default_factory=list)
    verified_evidence: list[str] = field(default_factory=list)
    current_blocker: str = ""
    next_action: str = ""
    duplicate_action_warning: bool = False
    checkpoint_id: str = ""
    rollback_point: str = ""
    status: str = "REQUIRES_REVIEW"

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "workspace": self.workspace,
            "completed_actions": list(self.completed_actions),
            "verified_evidence": list(self.verified_evidence),
            "current_blocker": self.current_blocker,
            "next_action": self.next_action,
            "duplicate_action_warning": self.duplicate_action_warning,
            "checkpoint_id": self.checkpoint_id,
            "rollback_point": self.rollback_point,
            "status": self.status,
        }


def _clean_items(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError("list fields must be arrays")
    result = tuple(str(v)[:500] for v in values if isinstance(v, str) and v.strip())
    return result


def evaluate(record: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a task record. No I/O or execution is performed."""
    if not isinstance(record, Mapping):
        raise ValueError("record must be an object")
    task_id = str(record.get("task_id") or "").strip()
    agent = str(record.get("agent") or "").strip()
    workspace = str(record.get("workspace") or "").strip()
    if not task_id or not agent or not workspace:
        return PlannerOutput(
            "",
            agent,
            workspace,
            status="REQUIRES_REVIEW",
            next_action="provide task_id, agent and workspace",
        ).as_dict()

    completed = _clean_items(record.get("completed_actions"))
    evidence = _clean_items(record.get("verified_evidence"))
    errors = _clean_items(record.get("error_fingerprints"))
    checkpoint = str(record.get("checkpoint_id") or "").strip()[:500]
    blocker = str(record.get("blocker") or "").strip()[:500]
    rollback = str(record.get("rollback_point") or "").strip()[:500]
    requested = str(record.get("next_action") or "").strip()[:500]
    parent_event_id = str(record.get("parent_event_id") or "").strip()[:500]

    if "parent_trace_id" in record:
        return PlannerOutput(
            task_id,
            agent,
            workspace,
            current_blocker="invalid lineage field: parent_trace_id",
            status="REQUIRES_REVIEW",
            next_action="replace parent_trace_id with parent_event_id",
        ).as_dict()
    if parent_event_id and not isinstance(record.get("parent_event_id"), str):
        return PlannerOutput(
            task_id,
            agent,
            workspace,
            current_blocker="parent_event_id must be a string",
            status="REQUIRES_REVIEW",
        ).as_dict()

    repeated_error = len(errors) >= 2 and len(set(errors[-2:])) == 1
    if blocker or repeated_error:
        reason = blocker or f"repeated error fingerprint: {errors[-1]}"
        return PlannerOutput(
            task_id,
            agent,
            workspace,
            list(completed),
            list(evidence),
            reason,
            "operator review; do not retry automatically",
            True,
            checkpoint,
            rollback,
            "BLOCKED",
        ).as_dict()
    if checkpoint and completed and evidence and requested in completed:
        return PlannerOutput(
            task_id,
            agent,
            workspace,
            list(completed),
            list(evidence),
            "",
            "do not repeat verified action",
            True,
            checkpoint,
            rollback,
            "ALREADY_VERIFIED",
        ).as_dict()
    if checkpoint:
        return PlannerOutput(
            task_id,
            agent,
            workspace,
            list(completed),
            list(evidence),
            "",
            requested or "resume smallest incomplete action",
            False,
            checkpoint,
            rollback,
            "RESUME_FROM_CHECKPOINT",
        ).as_dict()
    if not completed and not evidence:
        return PlannerOutput(
            task_id,
            agent,
            workspace,
            [],
            [],
            "",
            requested or "perform bounded first read",
            False,
            "",
            rollback,
            "NEW_TASK",
        ).as_dict()
    if not evidence:
        return PlannerOutput(
            task_id,
            agent,
            workspace,
            list(completed),
            [],
            "",
            "collect bounded verification evidence",
            False,
            checkpoint,
            rollback,
            "REQUIRES_REVIEW",
        ).as_dict()
    return PlannerOutput(
        task_id,
        agent,
        workspace,
        list(completed),
        list(evidence),
        "",
        requested or "continue with one bounded verified step",
        False,
        checkpoint,
        rollback,
        "READY_FOR_NEXT_STEP",
    ).as_dict()
