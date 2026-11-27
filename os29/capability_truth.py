"""Pure capability-truth reconciliation for bounded catalog metadata."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _names(items: Iterable[Any]) -> set[str]:
    result: set[str] = set()
    for item in items:
        if isinstance(item, str) and item:
            result.add(item)
        elif isinstance(item, Mapping) and isinstance(item.get("name"), str) and item["name"]:
            result.add(item["name"])
    return result


def reconcile(
    source: Iterable[Any],
    registry: Iterable[Any],
    gateway: Iterable[Any],
    bridge: Iterable[Any],
) -> dict[str, Any]:
    """Compare supplied names only; never discovers or calls a provider."""
    sets = {
        "source": _names(source),
        "registry": _names(registry),
        "gateway": _names(gateway),
        "bridge": _names(bridge),
    }
    union = set().union(*sets.values())
    rows = []
    for name in sorted(union):
        present = {key: name in value for key, value in sets.items()}
        if all(present.values()):
            status = "LIVE_CANDIDATE"
        elif present["source"] and not present["registry"]:
            status = "SOURCE_ONLY"
        elif present["registry"] and not present["gateway"]:
            status = "BACKEND_ONLY"
        elif present["gateway"] and not present["bridge"]:
            status = "GATEWAY_ONLY"
        else:
            status = "PARTIAL_REACHABILITY"
        rows.append({"name": name, **present, "status": status})
    return {
        "status": "RECONCILED_INPUTS",
        "counts": {key: len(value) for key, value in sets.items()},
        "rows": rows,
        "unverified": True,
        "side_effects": [],
    }
