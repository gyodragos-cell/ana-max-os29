"""Pure recommendation facade for Agent Reliability MVP."""
from __future__ import annotations

from typing import Any, Mapping

from .anti_repeat import evaluate
from .sentinel import evaluate_snapshot
from .capability_truth import reconcile


def recommend(task_record: Mapping[str, Any], runtime_snapshot: Mapping[str, Any], catalogs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return evidence-only planner and sentinel results; never executes actions."""
    planner = evaluate(task_record)
    sentinel = evaluate_snapshot(runtime_snapshot)
    catalog_result = None
    if catalogs is not None:
        catalog_result = reconcile(
            catalogs.get("source", []), catalogs.get("registry", []),
            catalogs.get("gateway", []), catalogs.get("bridge", []),
        )
    return {
        "planner": planner,
        "sentinel": sentinel,
        "capability_truth": catalog_result,
        "recommendation_only": True,
        "actions_executed": [],
        "lineage_field": "parent_event_id",
    }
