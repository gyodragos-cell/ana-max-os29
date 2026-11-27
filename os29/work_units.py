from __future__ import annotations

import builtins
import json
from copy import deepcopy
from typing import Any

from .models import TraceEvent, utc_now
from .store import Store

WORK_UNIT_SCHEMA = "os29.work_unit.v1"
_VALID_STATUSES = {"active", "handoff_ready", "completed", "blocked"}
_VALID_OUTCOMES = {"observed", "success", "failure", "error", "blocked", "unknown"}


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _text_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return [item.strip() for item in value]


class WorkUnitService:
    """Work-unit continuity built on OS29's canonical capsule and trace primitives."""

    def __init__(self, store: Store):
        self.store = store

    def _load(self, work_id: str) -> dict[str, Any]:
        work_id = _required_text(work_id, "work_id")
        envelope = self.store.get_capsule(work_id)
        if not envelope:
            raise ValueError("work unit not found")
        capsule = envelope.get("capsule")
        if not isinstance(capsule, dict):
            raise ValueError("work unit capsule is invalid")
        unit = capsule.get("work_unit")
        if (
            not isinstance(unit, dict)
            or unit.get("schema") != WORK_UNIT_SCHEMA
            or unit.get("work_id") != work_id
        ):
            raise ValueError("mission capsule is not an OS29 Work Unit V1")
        return envelope

    @staticmethod
    def _summary(envelope: dict[str, Any]) -> dict[str, Any]:
        capsule = envelope["capsule"]
        unit = capsule["work_unit"]
        return {
            "work_id": unit["work_id"],
            "project": capsule["project"],
            "objective": capsule["objective"],
            "status": capsule.get("status", "active"),
            "owner_agent": unit["owner_agent"],
            "updated_at": envelope["updated_at"],
            "next_action": capsule["next_steps"][0] if capsule["next_steps"] else None,
            "open_issue_count": len(capsule["open_issues"]),
        }

    def create(
        self,
        *,
        work_id: str,
        project: str,
        objective: str,
        owner_agent: str,
        allowed_scope: list[str],
        current_state: dict[str, Any],
        known_good: list[str],
        known_bad: list[str],
        open_issues: list[str],
        next_steps: list[str],
        context_refs: list[str],
    ) -> dict[str, Any]:
        work_id = _required_text(work_id, "work_id")
        if self.store.get_capsule(work_id):
            raise ValueError("work_id already exists; use handoff or evidence receipt instead")
        if not isinstance(current_state, dict):
            raise ValueError("current_state must be a JSON object")
        now = utc_now()
        capsule: dict[str, Any] = {
            "project": _required_text(project, "project"),
            "objective": _required_text(objective, "objective"),
            "status": "active",
            "current_state": deepcopy(current_state),
            "known_good": _text_list(known_good, "known_good"),
            "known_bad": _text_list(known_bad, "known_bad"),
            "open_issues": _text_list(open_issues, "open_issues"),
            "next_steps": _text_list(next_steps, "next_steps"),
            "work_unit": {
                "schema": WORK_UNIT_SCHEMA,
                "work_id": work_id,
                "owner_agent": _required_text(owner_agent, "owner_agent"),
                "created_by": _required_text(owner_agent, "owner_agent"),
                "title": _required_text(project, "project")
                + ": "
                + _required_text(objective, "objective")[:100],
                "revision": 1,
                "files_touched": [],
                "tools_used": [],
                "tests": [],
                "artifacts": [],
                "allowed_scope": _text_list(allowed_scope, "allowed_scope"),
                "context_refs": _text_list(context_refs, "context_refs"),
                "created_at": now,
                "handoff": None,
            },
        }
        transition = TraceEvent(
            trace_id=work_id,
            source="os29.work_units",
            component="work_unit_service",
            kind="work_unit.created",
            action="create",
            outcome="success",
            mission_id=work_id,
            attributes={
                "owner_agent": capsule["work_unit"]["owner_agent"],
                "status": "active",
            },
        )
        saved = self.store.create_work_unit_capsule(work_id, capsule, event=transition)
        event = saved["event"]
        return {
            **self._summary(saved),
            "event_id": event["event_id"],
            "redactions": saved["redactions"],
        }

    def get(self, *, work_id: str) -> dict[str, Any]:
        envelope = self._load(work_id)
        capsule = envelope["capsule"]
        unit = capsule["work_unit"]
        return {
            **self._summary(envelope),
            "revision": unit.get("revision", 1),
            "title": unit.get("title", capsule["project"]),
            "created_by": unit.get("created_by", unit["owner_agent"]),
            "created_at": unit["created_at"],
            "files_touched": unit.get("files_touched", []),
            "tools_used": unit.get("tools_used", []),
            "tests": unit.get("tests", []),
            "artifacts": unit.get("artifacts", []),
            "current_state": capsule["current_state"],
            "known_good": capsule["known_good"],
            "known_bad": capsule["known_bad"],
            "open_issues": capsule["open_issues"],
            "next_steps": capsule["next_steps"],
            "allowed_scope": unit["allowed_scope"],
            "context_refs": unit["context_refs"],
            "handoff": unit.get("handoff"),
        }

    def list(self, *, limit: int = 50) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for envelope in self.store.list_capsules(limit=max(1, min(int(limit) * 10, 1000))):
            capsule = envelope.get("capsule", {})
            unit = capsule.get("work_unit") if isinstance(capsule, dict) else None
            if isinstance(unit, dict) and unit.get("schema") == WORK_UNIT_SCHEMA:
                items.append(self._summary(envelope))
                if len(items) >= int(limit):
                    break
        return {"count": len(items), "work_units": items}

    def record_evidence_receipt(
        self,
        *,
        work_id: str,
        actor_agent: str,
        action: str,
        outcome: str,
        evidence: dict[str, Any],
        next_action: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._load(work_id)
        if idempotency_key is not None:
            idempotency_key = _required_text(idempotency_key, "idempotency_key")
        if outcome not in _VALID_OUTCOMES:
            raise ValueError("outcome must be a valid OS29 trace outcome")
        if not isinstance(evidence, dict):
            raise ValueError("evidence must be a JSON object")
        actor_agent = _required_text(actor_agent, "actor_agent")
        action = _required_text(action, "action")
        next_action = _required_text(next_action, "next_action")
        if idempotency_key is not None:
            for existing in self.store.list_trace(work_id):
                attrs = existing.get("attributes", {})
                if (
                    existing.get("kind") == "work_unit.evidence_receipt"
                    and attrs.get("idempotency_key") == idempotency_key
                ):
                    if (
                        existing.get("action") != action
                        or existing.get("outcome") != outcome
                        or attrs.get("actor_agent") != actor_agent
                        or attrs.get("evidence") != evidence
                    ):
                        raise ValueError("idempotency key conflicts with existing evidence")
                    return {
                        "work_id": work_id,
                        "event_id": existing["event_id"],
                        "trace_id": work_id,
                        "outcome": outcome,
                        "idempotent_replay": True,
                    }
        event = self.store.record_event(
            TraceEvent(
                trace_id=work_id,
                source="os29.work_units",
                component="work_unit_service",
                kind="work_unit.evidence_receipt",
                action=_required_text(action, "action"),
                outcome=outcome,
                mission_id=work_id,
                attributes={
                    "actor_agent": actor_agent,
                    "evidence": deepcopy(evidence),
                    "next_action": next_action,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        return {
            "work_id": work_id,
            "event_id": event["event_id"],
            "trace_id": work_id,
            "outcome": outcome,
        }

    def handoff(
        self,
        *,
        work_id: str,
        from_agent: str,
        to_agent: str,
        summary: str,
        next_action: str,
    ) -> dict[str, Any]:
        envelope = self._load(work_id)
        capsule = deepcopy(envelope["capsule"])
        from_agent = _required_text(from_agent, "from_agent")
        to_agent = _required_text(to_agent, "to_agent")
        if capsule["status"] == "completed":
            raise ValueError("cannot hand off a completed Work Unit")
        previous_handoff = capsule["work_unit"].get("handoff")
        if (
            capsule["status"] == "handoff_ready"
            and isinstance(previous_handoff, dict)
            and previous_handoff.get("from_agent") == from_agent
            and previous_handoff.get("to_agent") == to_agent
            and capsule["next_steps"]
            and capsule["next_steps"][0] == next_action
        ):
            return {**self._summary(envelope), "idempotent_replay": True}
        if capsule["work_unit"]["owner_agent"] != from_agent:
            raise ValueError("handoff sender must match the current Work Unit owner")
        capsule["status"] = "handoff_ready"
        capsule["next_steps"] = [_required_text(next_action, "next_action")] + [
            step for step in capsule["next_steps"] if step != next_action
        ]
        capsule["work_unit"]["owner_agent"] = to_agent
        capsule["work_unit"]["revision"] = capsule["work_unit"].get("revision", 1) + 1
        capsule["work_unit"]["handoff"] = {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "summary": _required_text(summary, "summary"),
            "at": utc_now(),
        }
        transition = TraceEvent(
            trace_id=work_id,
            source="os29.work_units",
            component="work_unit_service",
            kind="work_unit.handoff",
            action="handoff",
            outcome="success",
            mission_id=work_id,
            attributes={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "next_action": capsule["next_steps"][0],
            },
        )
        saved = self.store.save_work_unit_if_revision(
            work_id,
            capsule,
            expected_revision=envelope["capsule"]["work_unit"].get("revision", 1),
            event=transition,
        )
        event = saved["event"]
        return {**self._summary(saved), "event_id": event["event_id"]}

    def resume(self, *, work_id: str, agent_id: str) -> dict[str, Any]:
        result = self.get(work_id=work_id)
        events = self.store.list_trace(result["work_id"])
        receipts = [event for event in events if event.get("kind") == "work_unit.evidence_receipt"]
        result["resumed_by"] = _required_text(agent_id, "agent_id")
        result["latest_evidence_receipt"] = receipts[-1] if receipts else None
        result["evidence_receipt_count"] = len(receipts)
        last_receipt = receipts[-1] if receipts else None
        last_evidence = (
            last_receipt.get("attributes", {}).get("evidence", {}) if last_receipt else {}
        )
        context_lines = [
            "OS29 Work Unit " + result["work_id"],
            "Objective: " + result["objective"],
            "State: " + result["status"] + "; owner: " + result["owner_agent"],
            "Revision: " + str(result["revision"]),
            "Current: "
            + json.dumps(result["current_state"], ensure_ascii=False, sort_keys=True)[:420],
            "Verified good: " + "; ".join(result["known_good"][-3:]),
            "Known bad: " + "; ".join(result["known_bad"][-2:]),
            "Blockers: " + "; ".join(result["open_issues"][-3:]),
            "Files: " + "; ".join(result["files_touched"][-4:]),
            "Next: " + (result["next_action"] or "(none)"),
            "Evidence receipts: " + str(len(receipts)),
        ]
        if last_receipt:
            context_lines.append(
                "Last evidence: "
                + last_receipt["outcome"]
                + " event="
                + last_receipt["event_id"]
                + " command="
                + str(last_evidence.get("command", "not recorded"))[:120]
                + " exit="
                + str(last_evidence.get("exit_code", "unverified"))
            )
        result["context_pack"] = " | ".join(context_lines)[:1400]
        result["context_pack_words"] = len(result["context_pack"].split())
        return result

    def checkpoint(
        self,
        *,
        work_id: str,
        actor_agent: str,
        expected_revision: int,
        current_state: dict[str, Any],
        next_steps: builtins.list[str],
        files_touched: builtins.list[str] | None = None,
        tools_used: builtins.list[str] | None = None,
        tests: builtins.list[dict[str, Any]] | None = None,
        artifacts: builtins.list[str] | None = None,
        open_issues: builtins.list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Atomic, versioned checkpoint with replay-safe idempotency key."""
        actor_agent = _required_text(actor_agent, "actor_agent")
        if not isinstance(current_state, dict):
            raise ValueError("current_state must be an object")
        if not isinstance(expected_revision, int) or expected_revision < 1:
            raise ValueError("expected_revision must be positive")
        if idempotency_key is not None:
            idempotency_key = _required_text(idempotency_key, "idempotency_key")
            for event in self.store.list_trace(work_id):
                if (
                    event.get("kind") == "work_unit.checkpoint"
                    and event.get("attributes", {}).get("idempotency_key") == idempotency_key
                ):
                    return {
                        **self.get(work_id=work_id),
                        "idempotent_replay": True,
                        "event_id": event["event_id"],
                    }
        envelope = self._load(work_id)
        capsule = deepcopy(envelope["capsule"])
        unit = capsule["work_unit"]
        if unit.get("revision", 1) != expected_revision:
            raise ValueError("work unit revision conflict: reload and retry")
        if capsule["status"] == "completed":
            raise ValueError("cannot checkpoint a completed Work Unit")
        if tests is not None:
            if not isinstance(tests, list) or any(not isinstance(t, dict) for t in tests):
                raise ValueError("tests must be a list of objects")
            json.dumps(tests, allow_nan=False)
            unit["tests"] = deepcopy(tests)
        for field_name, value in (
            ("files_touched", files_touched),
            ("tools_used", tools_used),
            ("artifacts", artifacts),
        ):
            if value is not None:
                unit[field_name] = _text_list(value, field_name)
        if open_issues is not None:
            capsule["open_issues"] = _text_list(open_issues, "open_issues")
        capsule["current_state"] = deepcopy(current_state)
        capsule["next_steps"] = _text_list(next_steps, "next_steps")
        capsule["status"] = "active"
        unit["revision"] = expected_revision + 1
        transition = TraceEvent(
            trace_id=work_id,
            source="os29.work_units",
            component="work_unit_service",
            kind="work_unit.checkpoint",
            action="checkpoint",
            outcome="observed",
            mission_id=work_id,
            attributes={
                "actor_agent": actor_agent,
                "revision": expected_revision + 1,
                "idempotency_key": idempotency_key,
                "next_action": capsule["next_steps"][0] if capsule["next_steps"] else "",
                "files_touched": unit.get("files_touched", []),
                "test_count": len(unit.get("tests", [])),
            },
        )
        saved = self.store.save_work_unit_if_revision(
            work_id,
            capsule,
            expected_revision=expected_revision,
            event=transition,
        )
        event = saved["event"]
        return {
            **self._summary(saved),
            "revision": unit["revision"],
            "event_id": event["event_id"],
            "idempotent_replay": False,
        }

    def complete(self, *, work_id: str, actor_agent: str, expected_revision: int) -> dict[str, Any]:
        """Require persisted executable-test evidence before marking completed."""
        actor_agent = _required_text(actor_agent, "actor_agent")
        envelope = self._load(work_id)
        capsule = deepcopy(envelope["capsule"])
        unit = capsule["work_unit"]
        if capsule["status"] == "completed":
            return {
                **self._summary(envelope),
                "revision": unit.get("revision", 1),
                "idempotent_replay": True,
            }
        if unit.get("revision", 1) != expected_revision:
            raise ValueError("work unit revision conflict: reload and retry")

        def is_executed_test(proof: Any) -> bool:
            return (
                isinstance(proof, dict)
                and isinstance(proof.get("command"), str)
                and bool(proof["command"].strip())
                and type(proof.get("exit_code")) is int
                and proof["exit_code"] == 0
                and isinstance(proof.get("stdout"), str)
            )

        proofs: list[dict[str, Any]] = []
        for event in self.store.list_trace(work_id):
            if (
                event.get("kind") != "work_unit.evidence_receipt"
                or event.get("outcome") != "success"
            ):
                continue
            attrs = event.get("attributes", {})
            if attrs.get("actor_agent") != actor_agent:
                continue
            details = attrs.get("evidence")
            if not isinstance(details, dict):
                continue
            if is_executed_test(details) or any(
                is_executed_test(details.get(test_name)) for test_name in ("smoke", "pytest")
            ):
                proofs.append(event)
        if not proofs:
            raise ValueError(
                "completion requires the completing agent's persisted success "
                "evidence receipt with executable command, exit_code=0, and stdout"
            )
        capsule["status"] = "completed"
        capsule["next_steps"] = []
        unit["revision"] = expected_revision + 1
        transition = TraceEvent(
            trace_id=work_id,
            source="os29.work_units",
            component="work_unit_service",
            kind="work_unit.completed",
            action="complete",
            outcome="success",
            mission_id=work_id,
            attributes={
                "actor_agent": actor_agent,
                "verification_event_ids": [proof["event_id"] for proof in proofs],
                "revision": expected_revision + 1,
            },
        )
        saved = self.store.save_work_unit_if_revision(
            work_id,
            capsule,
            expected_revision=expected_revision,
            event=transition,
        )
        event = saved["event"]
        return {
            **self._summary(saved),
            "revision": unit["revision"],
            "event_id": event["event_id"],
            "idempotent_replay": False,
        }

    def fail(
        self, *, work_id: str, actor_agent: str, expected_revision: int, reason: str
    ) -> dict[str, Any]:
        """Persist a blocked work unit without discarding evidence."""
        envelope = self._load(work_id)
        capsule = deepcopy(envelope["capsule"])
        if capsule["status"] == "completed":
            raise ValueError("cannot fail a completed Work Unit")
        unit = capsule["work_unit"]
        if unit.get("revision", 1) != expected_revision:
            raise ValueError("work unit revision conflict: reload and retry")
        reason = _required_text(reason, "reason")
        capsule["status"] = "blocked"
        capsule["open_issues"] = capsule["open_issues"] + [reason]
        unit["revision"] = expected_revision + 1
        transition = TraceEvent(
            trace_id=work_id,
            source="os29.work_units",
            component="work_unit_service",
            kind="work_unit.blocked",
            action="fail",
            outcome="blocked",
            mission_id=work_id,
            attributes={
                "actor_agent": _required_text(actor_agent, "actor_agent"),
                "reason": reason,
                "revision": expected_revision + 1,
            },
        )
        saved = self.store.save_work_unit_if_revision(
            work_id,
            capsule,
            expected_revision=expected_revision,
            event=transition,
        )
        event = saved["event"]
        return {
            **self._summary(saved),
            "revision": unit["revision"],
            "event_id": event["event_id"],
        }

    def receipt(self, *, work_id: str) -> dict[str, Any]:
        """Reconstruct machine-readable and human-readable receipts from OS29."""
        work = self.get(work_id=work_id)
        events = self.store.list_trace(work_id)
        evidence_events = [e for e in events if e.get("kind") == "work_unit.evidence_receipt"]
        actions = [
            {
                "event_id": e["event_id"],
                "action": e["action"],
                "outcome": e["outcome"],
                "at": e["timestamp"],
                "actor_agent": e.get("attributes", {}).get("actor_agent"),
            }
            for e in events
            if e.get("kind", "").startswith("work_unit.")
        ]
        receipt = {
            "schema": "os29.work_unit_receipt.v1",
            "work_id": work_id,
            "trace_id": work_id,
            "title": work["title"],
            "objective": work["objective"],
            "status": work["status"],
            "created_by": work["created_by"],
            "assigned_agent": work["owner_agent"],
            "files_touched": work["files_touched"],
            "tools_used": work["tools_used"],
            "tests": work["tests"],
            "artifacts": work["artifacts"],
            "blockers": work["open_issues"],
            "next_action": work["next_action"],
            "actions": actions,
            "evidence": [
                {
                    "event_id": e["event_id"],
                    "outcome": e["outcome"],
                    "action": e["action"],
                    "actor_agent": e.get("attributes", {}).get("actor_agent"),
                    "details": e.get("attributes", {}).get("evidence", {}),
                }
                for e in evidence_events
            ],
        }
        lines = [
            f"# Evidence Receipt — {work['title']}",
            "",
            f"**Work Unit:** {work_id}",
            f"**Status:** {work['status']}",
            f"**Objective:** {work['objective']}",
            f"**Created by:** {work['created_by']}",
            f"**Assigned agent:** {work['owner_agent']}",
            "",
            "## Actions",
        ]
        for a in actions:
            lines.append(
                f"- {a['at']} | {a['actor_agent'] or 'system'} | "
                f"{a['action']} | {a['outcome']} | {a['event_id']}"
            )
        lines.extend(["", "## Tests and evidence"])
        for e in receipt["evidence"]:
            details = e["details"]
            label = f"- {e['actor_agent'] or 'unknown'}: {e['action']} ({e['outcome']})"
            checks: list[tuple[str, dict[str, Any]]] = []
            if isinstance(details.get("command"), str):
                checks.append(("command", details))
            for name in ("smoke", "pytest"):
                value = details.get(name)
                if isinstance(value, dict) and isinstance(value.get("command"), str):
                    checks.append((name, value))
            if not checks:
                lines.append(label + ", command='not supplied', exit_code='not verified'")
                continue
            lines.append(label)
            for name, check in checks:
                exit_code = check.get("exit_code", "not verified")
                lines.append(f"  - {name}: command={check['command']!r}, exit_code={exit_code!r}")
                for stream in ("stdout", "stderr"):
                    if isinstance(check.get(stream), str):
                        lines.append(f"    - {stream}: {check[stream][:500]}")
        lines.extend(["", "## Files and artifacts"])
        for filename in work["files_touched"] + work["artifacts"]:
            lines.append(f"- {filename}")
        lines.extend(["", "## Blockers"])
        for issue in work["open_issues"]:
            lines.append(f"- {issue}")
        if not work["open_issues"]:
            lines.append("- None recorded")
        lines.extend(["", "## Next action", work["next_action"] or "None; work unit is complete"])
        return {"receipt": receipt, "markdown": "\n".join(lines) + "\n"}

    def export_receipt(self, *, work_id: str) -> dict[str, Any]:
        """Export JSON/Markdown alongside the canonical OS29 DB on D:."""
        exported = self.receipt(work_id=work_id)
        safe_id = _required_text(work_id, "work_id")
        if any(
            ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
            for ch in safe_id
        ):
            raise ValueError(
                "work_id must contain only letters, numbers, dot, underscore or hyphen"
            )
        folder = self.store.db_path.parent / "artifacts" / "work_units"
        folder.mkdir(parents=True, exist_ok=True)
        json_path = folder / (safe_id + ".receipt.json")
        markdown_path = folder / (safe_id + ".receipt.md")
        json_tmp = folder / ("." + safe_id + ".json.tmp")
        markdown_tmp = folder / ("." + safe_id + ".md.tmp")
        json_tmp.write_text(
            json.dumps(exported["receipt"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        markdown_tmp.write_text(exported["markdown"], encoding="utf-8")
        json_tmp.replace(json_path)
        markdown_tmp.replace(markdown_path)
        return {
            "work_id": work_id,
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
            "status": exported["receipt"]["status"],
        }
