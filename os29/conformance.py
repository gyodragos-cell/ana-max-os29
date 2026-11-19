"""Bounded, non-executing agent conformance classification."""
from __future__ import annotations
from typing import Mapping

REQUIRED = ("contracts", "evidence", "trace", "checkpoint", "gateway", "anti_repeat", "sentinel", "observability")


def certify(agent: str, results: Mapping[str, bool]) -> dict:
    missing = [k for k in REQUIRED if k not in results]
    failed = [k for k in REQUIRED if k in results and not results[k]]
    if failed or len(failed) == len(REQUIRED):
        status = "REJECTED" if len(failed) == len(REQUIRED) else "LIMITED"
    elif missing:
        status = "LIMITED"
    else:
        status = "CERTIFIED"
    return {"agent": agent, "status": status, "missing": missing, "failed": failed, "evidence_only": True}
