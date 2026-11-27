"""Deterministic evidence freshness classification."""

from __future__ import annotations

from datetime import UTC, datetime


def classify(
    timestamp: str,
    now: datetime | None = None,
    fresh_seconds: int = 300,
    aging_seconds: int = 3600,
    stale_seconds: int = 86400,
) -> str:
    observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    current = now or datetime.now(UTC)
    age = max(0.0, (current - observed).total_seconds())
    if age <= fresh_seconds:
        return "LIVE_CURRENT"
    if age <= aging_seconds:
        return "FRESH"
    if age <= stale_seconds:
        return "AGING"
    if age <= stale_seconds * 7:
        return "STALE"
    return "EXPIRED"
