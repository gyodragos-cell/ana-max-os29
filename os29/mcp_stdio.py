from __future__ import annotations

import datetime
import json
import os
import socket
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .diagnosis import diagnose_trace
from .intelligence import build_intelligence_report
from .local_answer import DEFAULT_MODEL, answer_from_memory
from .mcp_policy import (
    CapabilityPolicy,
    PolicyDenied,
    bounded_command,
    bounded_file_read,
    bounded_literal_search,
)
from .mcp_validation import (
    MAX_OUTPUT_BYTES,
    iter_frames,
    parse_message,
    validate_json,
    validate_tool_arguments,
)
from .models import TraceEvent, new_id
from .retrieval import refresh_memory_index, search_memory
from .runtime_snapshot import snapshot_loopback
from .scope import ScopePolicy
from .store import Store
from .telemetry import (
    log_error,
    log_shutdown,
    log_startup,
    log_tool_call,
    log_tool_result,
)
from .tools import file_write
from .work_units import WorkUnitService

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("OS29_DB_PATH", str(ROOT / "data" / "os29.db")))
SCOPE_PATH = Path(
    os.environ.get("OS29_SCOPE_PATH", str(ROOT / "config" / "lab_scope.json"))
)
PROTOCOL_VERSION = "2024-11-05"

# ── Tower tools — compact lab context ────────────────────────────────────────

_TOWER_PORTS: dict[int, str] = {}

_AGENTS: list[dict[str, Any]] = []

_LAB_STACK = {
    "os": sys.platform,
    "python": sys.version.split()[0],
    "canonical_db": str(DB_PATH),
    "workspaces": [],
    "out_of_scope": [],
}


def _probe_port(port: int, timeout: float = 0.4) -> str:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return "UP"
    except OSError:
        return "DOWN"


def _capsule_payload(capsule_record: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the current Store envelope and the older payload envelope."""
    value = capsule_record.get("capsule")
    if isinstance(value, dict):
        return value
    value = capsule_record.get("payload")
    if isinstance(value, dict):
        return value
    return capsule_record


def _tower_bootstrap(
    store: Store, agent_id: str, mission_id: str | None = None
) -> dict[str, Any]:
    """~116 token compact lab context. Called first by any agent."""
    ts = datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")
    # Live port probe (fast, non-blocking)
    ports_live = {f"{p}_{name}": _probe_port(p) for p, name in _TOWER_PORTS.items()}
    # Active sessions (last 3) — store uses list_session_records
    try:
        sessions_raw = store.list_session_records(limit=3)
        sessions = [
            {
                "id": s.get("session_id", "?"),
                "title": s.get("title") or s.get("payload", {}).get("title", "?"),
            }
            for s in sessions_raw
        ]
    except Exception:
        sessions = []
    # Active mission if requested — store uses get_capsule(mission_id)
    mission = None
    if mission_id:
        try:
            cap = store.get_capsule(mission_id)
            if cap:
                p = _capsule_payload(cap)
                mission = {
                    "project": p.get("project", "?"),
                    "objective": p.get("objective", "?"),
                    "next_steps": p.get("next_steps", [])[:3],
                }
        except Exception:
            mission = {"error": f"mission {mission_id!r} not found"}
    return {
        "lab": "local installation",
        "profile": "user-configured",
        "canonical_db": _LAB_STACK["canonical_db"],
        "stack": _LAB_STACK,
        "agents": _AGENTS,
        "ports_live": ports_live,
        "recent_sessions": sessions,
        "active_mission": mission,
        "agent_id": agent_id,
        "timestamp_utc": ts,
        "hint": "Call os29_session_list(limit=3) and os29_memory_search(query=<topic>) for deeper context.",
    }


def _tower_resume(store: Store, mission_id: str) -> dict[str, Any]:
    """Return mission capsule as compact context (~116 tokens)."""
    try:
        cap = store.get_capsule(mission_id)
        if not cap:
            return {"error": f"Mission '{mission_id}' not found in OS29."}
        payload = _capsule_payload(cap)
        return {
            "mission_id": mission_id,
            "project": payload.get("project", "?"),
            "objective": payload.get("objective", "?"),
            "current_state": payload.get("current_state", {}),
            "next_steps": payload.get("next_steps", [])[:5],
            "open_issues": payload.get("open_issues", [])[:5],
            "known_good": payload.get("known_good", [])[:5],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tower_checkpoint(
    store: Store, mission_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Save a mission checkpoint to OS29."""
    required = {
        "project",
        "objective",
        "current_state",
        "known_good",
        "known_bad",
        "open_issues",
        "next_steps",
    }
    missing = required - set(payload.keys())
    if missing:
        return {
            "error": f"Missing required fields: {sorted(missing)}. Add them and retry."
        }
    try:
        result = store.save_capsule(mission_id, payload)
        return {"saved": True, "mission_id": mission_id, "result": result}
    except Exception as exc:
        return {"error": str(exc)}


def _tower_memory_search(
    store: Store, query: str, limit: int = 8, scope: str = "all"
) -> dict[str, Any]:
    """Search OS29 memory and return compact results via existing _dispatch logic."""
    source_map = {
        "all": None,
        "experience": ["experience"],
        "session": ["session"],
        "capsule": ["capsule"],
        "event": ["event"],
        "document": ["document"],
    }
    source_types = source_map.get(scope)
    try:
        # Use existing search_memory module function (same as os29_memory_search dispatch)
        raw_result = search_memory(
            store,
            query,
            limit=limit,
            include_candidates=False,
            source_types=source_types,
        )
        results = raw_result.get("results", [])
        compact = []
        for r in results:
            compact.append(
                {
                    "type": r.get("source_type", r.get("type", "?")),
                    "title": r.get("title", r.get("problem_key", r.get("kind", "?")))[
                        :80
                    ],
                    "snippet": str(
                        r.get("summary", r.get("solution", r.get("content", "")))
                    )[:200],
                }
            )
        return {
            "query": query,
            "scope": scope,
            "count": len(compact),
            "results": compact,
        }
    except Exception as exc:
        return {"error": str(exc), "query": query}


def schemas() -> list[dict[str, Any]]:
    def obj(
        properties: dict[str, Any] | None = None, required: list[str] | None = None
    ) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False,
        }

    string = {"type": "string"}
    integer = {"type": "integer", "minimum": 1, "maximum": 2000}
    string_list = {"type": "array", "items": string}
    return [
        {
            "name": "os29_status",
            "description": "Read-only counts/status of the persistent OS29 evidence store.",
            "inputSchema": obj(),
        },
        {
            "name": "os29_runtime_snapshot",
            "description": "Read-only HTTP health probes against fixed 127.0.0.1 OS28 ports; never starts/stops a service.",
            "inputSchema": obj(),
        },
        {
            "name": "os29_scope_check",
            "description": "Check an HTTP(S) target against the explicit OS29 lab allowlist; does not contact the target.",
            "inputSchema": obj({"target": string}, ["target"]),
        },
        {
            "name": "os29_trace_get",
            "description": "Read one persisted OS29 trace by trace_id.",
            "inputSchema": obj({"trace_id": string}, ["trace_id"]),
        },
        {
            "name": "os29_trace_diagnose",
            "description": "Summarize observed failures for a trace and create an incident record; root cause remains explicitly unverified.",
            "inputSchema": obj({"trace_id": string}, ["trace_id"]),
        },
        {
            "name": "os29_capabilities_list",
            "description": "Read the observed capability/world-model nodes and their evidence freshness timestamps.",
            "inputSchema": obj({"limit": integer}),
        },
        {
            "name": "os29_capability_edges_list",
            "description": "Read observed relationships between capability/world-model nodes.",
            "inputSchema": obj({"limit": integer}),
        },
        {
            "name": "os29_mission_capsule_get",
            "description": "Read a persistent OS29 mission capsule.",
            "inputSchema": obj({"mission_id": string}, ["mission_id"]),
        },
        {
            "name": "os29_mission_capsule_save",
            "description": "Persist an operator/agent mission checkpoint. Secrets are redacted; required state fields must be present.",
            "inputSchema": obj(
                {
                    "mission_id": string,
                    "capsule": obj(
                        {
                            "project": string,
                            "objective": string,
                            "current_state": {},
                            "known_good": {"type": "array"},
                            "known_bad": {"type": "array"},
                            "open_issues": {"type": "array"},
                            "next_steps": {"type": "array"},
                        },
                        [
                            "project",
                            "objective",
                            "current_state",
                            "known_good",
                            "known_bad",
                            "open_issues",
                            "next_steps",
                        ],
                    ),
                },
                ["mission_id", "capsule"],
            ),
        },
        {
            "name": "os29_work_unit_create",
            "description": "Create one canonical OS29 Work Unit V1. It reuses mission_capsules for state and trace_events for evidence; no parallel memory is created.",
            "inputSchema": obj(
                {
                    "work_id": string,
                    "project": string,
                    "objective": string,
                    "owner_agent": string,
                    "allowed_scope": string_list,
                    "current_state": {"type": "object"},
                    "known_good": string_list,
                    "known_bad": string_list,
                    "open_issues": string_list,
                    "next_steps": string_list,
                    "context_refs": string_list,
                },
                [
                    "work_id",
                    "project",
                    "objective",
                    "owner_agent",
                    "allowed_scope",
                    "current_state",
                    "known_good",
                    "known_bad",
                    "open_issues",
                    "next_steps",
                    "context_refs",
                ],
            ),
        },
        {
            "name": "os29_work_unit_verify",
            "description": "Verify a Work Unit hash chain with an optional independently recorded head.",
            "inputSchema": obj(
                {"work_id": string, "expected_head": string}, ["work_id"]
            ),
        },
        {
            "name": "os29_work_unit_get",
            "description": "Read one canonical OS29 Work Unit V1 by work_id.",
            "inputSchema": obj({"work_id": string}, ["work_id"]),
        },
        {
            "name": "os29_work_unit_list",
            "description": "List current OS29 Work Unit V1 summaries backed only by canonical mission capsules.",
            "inputSchema": obj(
                {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}
            ),
        },
        {
            "name": "os29_evidence_receipt_record",
            "description": "Append a durable evidence receipt to the Work Unit trace. Does not replace prior evidence.",
            "inputSchema": obj(
                {
                    "work_id": string,
                    "actor_agent": string,
                    "action": string,
                    "outcome": {
                        "type": "string",
                        "enum": [
                            "observed",
                            "success",
                            "failure",
                            "error",
                            "blocked",
                            "unknown",
                        ],
                    },
                    "evidence": {"type": "object"},
                    "next_action": string,
                    "idempotency_key": string,
                },
                [
                    "work_id",
                    "actor_agent",
                    "action",
                    "outcome",
                    "evidence",
                    "next_action",
                ],
            ),
        },
        {
            "name": "os29_work_unit_handoff",
            "description": "Hand a canonical OS29 Work Unit V1 from one agent to another; the receiving agent can resume with work_id only.",
            "inputSchema": obj(
                {
                    "work_id": string,
                    "from_agent": string,
                    "to_agent": string,
                    "summary": string,
                    "next_action": string,
                },
                ["work_id", "from_agent", "to_agent", "summary", "next_action"],
            ),
        },
        {
            "name": "os29_work_unit_resume",
            "description": "Recover a compact Work Unit V1 context using only its work_id, including last durable evidence receipt and next action.",
            "inputSchema": obj(
                {"work_id": string, "agent_id": string}, ["work_id", "agent_id"]
            ),
        },
        {
            "name": "os29_work_unit_checkpoint",
            "description": "Atomically update a canonical Work Unit with revision check, actual tests, files and next steps; replays with the same idempotency key do not duplicate events.",
            "inputSchema": obj(
                {
                    "work_id": string,
                    "actor_agent": string,
                    "expected_revision": integer,
                    "current_state": {"type": "object"},
                    "next_steps": string_list,
                    "files_touched": string_list,
                    "tools_used": string_list,
                    "tests": {"type": "array", "items": {"type": "object"}},
                    "artifacts": string_list,
                    "open_issues": string_list,
                    "idempotency_key": string,
                },
                [
                    "work_id",
                    "actor_agent",
                    "expected_revision",
                    "current_state",
                    "next_steps",
                ],
            ),
        },
        {
            "name": "os29_work_unit_complete",
            "description": "Complete only after persisted command/exit_code=0/stdout evidence; atomic version check.",
            "inputSchema": obj(
                {
                    "work_id": string,
                    "actor_agent": string,
                    "expected_revision": integer,
                },
                ["work_id", "actor_agent", "expected_revision"],
            ),
        },
        {
            "name": "os29_work_unit_fail",
            "description": "Mark a Work Unit blocked with a durable reason and revision check.",
            "inputSchema": obj(
                {
                    "work_id": string,
                    "actor_agent": string,
                    "expected_revision": integer,
                    "reason": string,
                },
                ["work_id", "actor_agent", "expected_revision", "reason"],
            ),
        },
        {
            "name": "os29_work_unit_receipt",
            "description": "Read canonical Work Unit Evidence Receipt as JSON and Markdown derived from the OS29 trace.",
            "inputSchema": obj({"work_id": string}, ["work_id"]),
        },
        {
            "name": "os29_work_unit_receipt_export",
            "description": "Write a canonical Evidence Receipt JSON and Markdown under a user-configured local receipt directory.",
            "inputSchema": obj({"work_id": string}, ["work_id"]),
        },
        {
            "name": "os29_session_save",
            "description": "Append one immutable, redacted ChatGPT/local session checkpoint for cross-account continuity. Identical retries are idempotent.",
            "inputSchema": obj(
                {
                    "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                    "payload": obj(
                        {
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "objective": string,
                            "decisions": {"type": "array"},
                            "tests": {"type": "array"},
                            "files_changed": {"type": "array"},
                            "incidents": {"type": "array"},
                            "next_steps": {"type": "array"},
                            "transcript_excerpt": string,
                            "conversation_id": string,
                            "started_at": string,
                            "ended_at": string,
                            "tags": {"type": "array"},
                            "project": string,
                            "conversation_part": integer,
                            "conversation_parts": integer,
                            "source_file": string,
                            "source_sha256": string,
                        },
                        ["title", "summary"],
                    ),
                    "source": {
                        "type": "string",
                        "enum": ["chatgpt_session", "chatgpt_export", "manual"],
                    },
                    "ended_at": string,
                },
                ["session_id", "payload"],
            ),
        },
        {
            "name": "os29_session_get",
            "description": "Retrieve a saved local session checkpoint by immutable session ID.",
            "inputSchema": obj({"session_id": string}, ["session_id"]),
        },
        {
            "name": "os29_session_list",
            "description": "List recent local session checkpoints.",
            "inputSchema": obj(
                {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}
            ),
        },
        {
            "name": "os29_trace_record",
            "description": "Persist one normalized os29.trace.v1 observation with automatic redaction.",
            "inputSchema": obj({"event": {"type": "object"}}, ["event"]),
        },
        {
            "name": "os29_experience_search",
            "description": "Search evidence-linked experience; only validated lessons are returned by default.",
            "inputSchema": obj(
                {
                    "query": string,
                    "include_candidates": {"type": "boolean"},
                    "limit": integer,
                },
                ["query"],
            ),
        },
        {
            "name": "os29_memory_search",
            "description": "Search the persistent local memory across trace events, incidents, mission capsules, capabilities, experiences and explicitly approved local text documents using redacted SQLite FTS5/BM25 retrieval. Candidate lessons are excluded by default; semantic embeddings are not enabled.",
            "inputSchema": obj(
                {
                    "query": string,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    "include_candidates": {"type": "boolean"},
                    "source_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "event",
                                "incident",
                                "capsule",
                                "experience",
                                "capability",
                                "document",
                                "session",
                            ],
                        },
                    },
                },
                ["query"],
            ),
        },
        {
            "name": "os29_memory_answer",
            "description": "Answer a question from approved OS29 evidence using structured citations and the already-running local Ollama at 127.0.0.1:11434 only. Never starts a model/service. Candidate/rejected evidence is excluded; invalid citations or answers needing review return MCP isError=true.",
            "inputSchema": obj(
                {
                    "query": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "model": {"type": "string", "maxLength": 120},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 6},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 90},
                    "num_ctx": {"type": "integer", "minimum": 512, "maximum": 4096},
                    "num_predict": {"type": "integer", "minimum": 16, "maximum": 512},
                    "source_types": {
                        "type": "array",
                        "maxItems": 6,
                        "items": {
                            "type": "string",
                            "enum": [
                                "event",
                                "incident",
                                "capsule",
                                "experience",
                                "capability",
                                "document",
                                "session",
                            ],
                        },
                    },
                    "retrieval_query": {"type": "string", "maxLength": 2000},
                },
                ["query"],
            ),
        },
        {
            "name": "os29_experience_validate",
            "description": "Validate and promote an experience candidate based on linked verification event.",
            "inputSchema": obj(
                {
                    "lesson_id": string,
                    "verification_event_id": string,
                    "verified_by": string,
                    "confidence": {"type": "number", "minimum": 0.5, "maximum": 1.0},
                },
                ["lesson_id", "verification_event_id", "verified_by"],
            ),
        },
        {
            "name": "os29_experience_candidate_add",
            "description": "Record an unvalidated candidate lesson linked to persisted source event IDs. This tool cannot mark a lesson validated.",
            "inputSchema": obj(
                {
                    "problem_key": string,
                    "cause": string,
                    "solution": string,
                    "outcome": {
                        "type": "string",
                        "enum": ["success", "failure", "partial", "unknown"],
                    },
                    "source_event_ids": {"type": "array", "items": string},
                },
                ["problem_key", "cause", "solution", "outcome", "source_event_ids"],
            ),
        },
        {
            "name": "os29_intelligence_report",
            "description": "Unified evidence-first Agent DNA, Memory of Failure/REM, Regret candidates, Skill Distillation and Discovery report. No auto-start, unverified causal claims or candidate promotion.",
            "inputSchema": obj(
                {"event_limit": {"type": "integer", "minimum": 1, "maximum": 1000}}
            ),
        },
        {
            "name": "os29_terminal_exec",
            "description": "Execute an operator-approved command alias (fixed argv, no shell) inside the configured workspace.",
            "inputSchema": obj(
                {"command": string, "cwd": string, "timeout_seconds": integer},
                ["command"],
            ),
        },
        {
            "name": "os29_file_read",
            "description": "Read file lines with safe bounds and encoding handling.",
            "inputSchema": obj(
                {"path": string, "start_line": integer, "end_line": integer}, ["path"]
            ),
        },
        {
            "name": "os29_file_write",
            "description": "Write or overwrite a file in the workspace.",
            "inputSchema": obj(
                {"path": string, "content": string, "overwrite": {"type": "boolean"}},
                ["path", "content"],
            ),
        },
        {
            "name": "os29_code_search",
            "description": "Search a literal text pattern within the configured workspace with bounded scanning.",
            "inputSchema": obj(
                {
                    "pattern": string,
                    "search_path": string,
                    "max_results": integer,
                    "case_sensitive": {"type": "boolean"},
                },
                ["pattern"],
            ),
        },
        # ── Tower tools ──────────────────────────────────────────────────────────
        {
            "name": "tower_bootstrap",
            "description": "Return a compact (~116 token) lab context for any agent at session start: stack, agents, live port status, recent sessions. Optionally loads an active mission capsule. CALL THIS FIRST.",
            "inputSchema": obj(
                {"agent_id": string, "mission_id": string}, ["agent_id"]
            ),
        },
        {
            "name": "tower_resume",
            "description": "Load a mission capsule from OS29 as compact context. Use to resume work without re-explaining everything.",
            "inputSchema": obj({"mission_id": string}, ["mission_id"]),
        },
        {
            "name": "tower_checkpoint",
            "description": "Save a mission checkpoint to OS29. Requires: project, objective, current_state, known_good, known_bad, open_issues, next_steps.",
            "inputSchema": obj(
                {"mission_id": string, "payload": {"type": "object"}},
                ["mission_id", "payload"],
            ),
        },
        {
            "name": "tower_memory_search",
            "description": "Search OS29 memory across all sources and return compact results. Scope: all|experience|session|capsule|event|document.",
            "inputSchema": obj(
                {
                    "query": string,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "scope": {
                        "type": "string",
                        "enum": [
                            "all",
                            "experience",
                            "session",
                            "capsule",
                            "event",
                            "document",
                        ],
                    },
                },
                ["query"],
            ),
        },
    ]


TOOL_SCHEMAS = {tool["name"]: tool["inputSchema"] for tool in schemas()}
TOOL_NAMES = set(TOOL_SCHEMAS)


def _content(value: Any, is_error: bool = False) -> dict[str, Any]:
    text = json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    )
    if len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        text = json.dumps({"error": "tool output exceeds limit"})
        is_error = True
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOL_SCHEMAS:
        raise ValueError(f"unknown OS29 tool: {name}")
    validate_tool_arguments(name, args, TOOL_SCHEMAS[name])
    policy = CapabilityPolicy.from_environment()
    trace_id = f"mcp-{new_id()[:8]}"
    try:
        args = policy.prepare(name, args)
    except PolicyDenied as exc:
        if policy.mode == "normal":
            Store(DB_PATH).record_event(
                TraceEvent(
                    trace_id=trace_id,
                    source="os29.mcp_policy",
                    component="capability_guard",
                    kind="mcp.policy.decision",
                    action=name,
                    outcome="blocked",
                    attributes={"reason": str(exc)},
                )
            )
        raise
    if policy.mode == "dry-run":
        return {
            "mode": "dry-run",
            "tool": name,
            "executed": False,
            "policy_allowed": True,
        }
    store = Store(DB_PATH, read_only=policy.mode == "read-only")
    _start = log_tool_call(name, trace_id)
    try:
        result = _dispatch(store, name, args, trace_id, policy=policy)
        if name == "os29_memory_answer" and isinstance(result, dict):
            outcome = (
                "success"
                if result.get("answer_status") in {"grounded", "evidence_insufficient"}
                else "failure"
            )
        else:
            outcome = (
                "failure"
                if isinstance(result, dict) and result.get("isError")
                else "success"
            )
        log_tool_result(name, trace_id, _start, outcome)
        return result
    except Exception as exc:
        log_error(name, exc, trace_id)
        raise


def _dispatch(
    store: Store,
    name: str,
    args: dict[str, Any],
    trace_id: str,
    *,
    policy: CapabilityPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or CapabilityPolicy()
    if name not in TOOL_NAMES:
        raise ValueError(f"unknown OS29 tool: {name}")
    if name == "os29_status":
        return store.stats()
    if name == "os29_runtime_snapshot":
        return snapshot_loopback(store)
    if name == "os29_scope_check":
        decision = ScopePolicy(SCOPE_PATH).check_target(args["target"])
        # Persist the decision and reason, but not the full target URL/path/query.
        store.record_event(
            TraceEvent(
                trace_id=f"scope-check-{new_id()}",
                source="os29.scope",
                component="scope_policy",
                kind="scope.decision",
                action="check_target",
                outcome="observed" if decision.get("allowed") else "blocked",
                attributes={
                    "allowed": bool(decision.get("allowed")),
                    "reason": str(decision.get("reason", "unknown")),
                    "host": str(decision.get("host", ""))[:255],
                    "port": decision.get("port"),
                    "scheme": str(decision.get("scheme", ""))[:16],
                },
            )
        )
        return decision
    if name == "os29_trace_get":
        trace_id = str(args["trace_id"])
        events = store.list_trace(trace_id)
        return {
            "trace_id": trace_id,
            "event_count": len(events),
            "events": events,
            "summary": store.trace_summary(trace_id),
        }
    if name == "os29_trace_diagnose":
        return diagnose_trace(store, str(args["trace_id"]))
    if name == "os29_capabilities_list":
        return {
            "capabilities": store.list_capabilities(limit=int(args.get("limit", 500)))
        }
    if name == "os29_capability_edges_list":
        return {
            "edges": store.list_capability_edges(limit=int(args.get("limit", 1000)))
        }
    if name == "os29_mission_capsule_get":
        value = store.get_capsule(str(args["mission_id"]))
        if not value:
            raise ValueError("mission capsule not found")
        return value
    if name == "os29_mission_capsule_save":
        return store.save_capsule(str(args["mission_id"]), args["capsule"])
    if name == "os29_work_unit_create":
        return WorkUnitService(store).create(**args)
    if name == "os29_work_unit_verify":
        return store.verify_work_unit(
            args["work_id"], expected_head=args.get("expected_head")
        )
    if name == "os29_work_unit_get":
        return WorkUnitService(store).get(work_id=str(args["work_id"]))
    if name == "os29_work_unit_list":
        return WorkUnitService(store).list(limit=int(args.get("limit", 50)))
    if name == "os29_evidence_receipt_record":
        return WorkUnitService(store).record_evidence_receipt(**args)
    if name == "os29_work_unit_handoff":
        return WorkUnitService(store).handoff(**args)
    if name == "os29_work_unit_resume":
        return WorkUnitService(store).resume(
            work_id=str(args["work_id"]), agent_id=str(args["agent_id"])
        )
    if name == "os29_work_unit_checkpoint":
        return WorkUnitService(store).checkpoint(**args)
    if name == "os29_work_unit_complete":
        return WorkUnitService(store).complete(**args)
    if name == "os29_work_unit_fail":
        return WorkUnitService(store).fail(**args)
    if name == "os29_work_unit_receipt":
        return WorkUnitService(store).receipt(work_id=str(args["work_id"]))
    if name == "os29_work_unit_receipt_export":
        return WorkUnitService(store).export_receipt(work_id=str(args["work_id"]))
    if name == "os29_session_save":
        saved = store.save_session_record(
            str(args["session_id"]),
            args["payload"],
            source=str(args.get("source", "chatgpt_session")),
            ended_at=args.get("ended_at"),
        )
        return {"saved": saved, "memory_index": refresh_memory_index(store)}
    if name == "os29_session_get":
        value = store.get_session_record(str(args["session_id"]))
        if not value:
            raise ValueError("session record not found")
        return value
    if name == "os29_session_list":
        return {
            "sessions": store.list_session_records(limit=int(args.get("limit", 20)))
        }
    if name == "os29_trace_record":
        event = TraceEvent.from_dict(args["event"])
        return store.record_event(event)
    if name == "os29_experience_search":
        include_candidates = bool(args.get("include_candidates", False))
        return {
            "query": str(args["query"]),
            "include_candidates": include_candidates,
            "experiences": store.search_experiences(
                str(args["query"]),
                include_candidates=include_candidates,
                limit=int(args.get("limit", 20)),
            ),
        }
    if name == "os29_memory_search":
        return search_memory(
            store,
            str(args["query"]),
            limit=int(args.get("limit", 10)),
            include_candidates=bool(args.get("include_candidates", False)),
            source_types=args.get("source_types", []),
        )
    if name == "os29_memory_answer":
        allowed = {
            "query",
            "model",
            "limit",
            "timeout_seconds",
            "num_ctx",
            "num_predict",
            "source_types",
            "retrieval_query",
        }
        unsupported = sorted(set(args) - allowed)
        if unsupported:
            raise ValueError(
                "unsupported os29_memory_answer arguments: " + ", ".join(unsupported)
            )
        return answer_from_memory(
            store,
            args["query"],
            model=args.get("model", DEFAULT_MODEL),
            limit=args.get("limit", 4),
            timeout_seconds=args.get("timeout_seconds", 45.0),
            num_ctx=args.get("num_ctx", 2048),
            num_predict=args.get("num_predict", 192),
            source_types=args.get("source_types"),
            retrieval_query=args.get("retrieval_query"),
        )
    if name == "os29_experience_validate":
        return store.validate_experience(
            lesson_id=str(args["lesson_id"]),
            verification_event_id=str(args["verification_event_id"]),
            verified_by=str(args["verified_by"]),
            confidence=float(args.get("confidence", 0.9)),
        )
    if name == "os29_experience_candidate_add":
        return store.record_experience(
            problem_key=str(args["problem_key"]),
            cause=str(args["cause"]),
            solution=str(args["solution"]),
            outcome=str(args["outcome"]),
            source_event_ids=[str(x) for x in args["source_event_ids"]],
            outcome_verified=False,
            verified_by=None,
            confidence=0.0,
        )
    if name == "os29_intelligence_report":
        return build_intelligence_report(
            store, event_limit=int(args.get("event_limit", 500))
        )
    if name == "os29_terminal_exec":
        alias = args["command"]
        if alias not in policy.commands:
            raise PolicyDenied("command_alias_not_approved")
        result = bounded_command(
            policy.commands[alias],
            args["cwd"],
            args["timeout_seconds"],
            policy.max_output_bytes,
        )
        store.record_event(
            TraceEvent(
                trace_id=trace_id,
                source="os29.terminal",
                component="terminal_exec",
                kind="exec.command",
                action=alias,
                outcome="success" if result["exit_code"] == 0 else "failure",
                attributes={
                    "exit_code": result["exit_code"],
                    "reason": result["reason"],
                },
            )
        )
        return result
    if name == "os29_file_read":
        return bounded_file_read(
            str(args["path"]),
            policy.max_file_bytes,
            start_line=args.get("start_line"),
            end_line=args.get("end_line"),
        )
    if name == "os29_file_write":
        return file_write(
            str(args["path"]),
            str(args["content"]),
            overwrite=bool(args.get("overwrite", True)),
        )
    if name == "os29_code_search":
        return bounded_literal_search(
            args["search_path"],
            args["pattern"],
            max_results=args.get("max_results", 50),
            case_sensitive=args.get("case_sensitive", False),
            policy=policy,
        )
    # ── Tower tools ──────────────────────────────────────────────────────────
    if name == "tower_bootstrap":
        return _tower_bootstrap(
            store, agent_id=str(args["agent_id"]), mission_id=args.get("mission_id")
        )
    if name == "tower_resume":
        return _tower_resume(store, mission_id=str(args["mission_id"]))
    if name == "tower_checkpoint":
        payload = args.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("tower_checkpoint: payload must be a JSON object")
        return _tower_checkpoint(
            store, mission_id=str(args["mission_id"]), payload=payload
        )
    if name == "tower_memory_search":
        return _tower_memory_search(
            store,
            query=str(args["query"]),
            limit=int(args.get("limit", 8)),
            scope=str(args.get("scope", "all")),
        )
    raise ValueError(f"unimplemented OS29 tool: {name}")


def handle(message: Any) -> dict[str, Any] | None:
    invalid = {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "Invalid Request"},
    }
    try:
        validate_json(message)
    except ValueError:
        return invalid
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return invalid
    method = message.get("method")
    request_id = message.get("id")
    if (
        not isinstance(method, str)
        or not method
        or type(request_id) not in {str, int, type(None)}
        or (isinstance(request_id, str) and len(request_id) > 256)
    ):
        return invalid
    # Never execute a tool call sent as a notification without a request ID.
    if "id" not in message:
        return None
    params = message.get("params", {})
    if not isinstance(params, dict):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": "Invalid params"},
        }
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {
                    "name": "os29-operational-intelligence",
                    "version": "0.1.0",
                },
                "capabilities": {"tools": {"listChanged": False}},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": schemas()}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "Invalid tool name"},
            }
        if not isinstance(args, dict):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _content({"error": "arguments_must_be_object"}, True),
            }
        try:
            result = call_tool(str(name), args)
            mcp_tool_error = (
                str(name) == "os29_memory_answer"
                and isinstance(result, dict)
                and result.get("answer_status")
                not in {"grounded", "evidence_insufficient"}
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _content(result, is_error=mcp_tool_error),
            }
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": _content({"error": str(exc)}, True),
            }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "Method not found"},
    }


def encode_response(response: dict[str, Any]) -> str:
    """Serialize one JSON-RPC response using ASCII escapes for Windows code-page safety."""
    text = (
        json.dumps(response, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    )
    if len(text) > MAX_OUTPUT_BYTES:
        return (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": response.get("id"),
                    "error": {"code": -32000, "message": "Response exceeds limit"},
                },
                ensure_ascii=True,
            )
            + "\n"
        )
    return text


def main() -> None:
    # MCP stdio framing is one JSON-RPC message per UTF-8 line. stdout is protocol-only.
    log_startup("os29-operational-intelligence", str(DB_PATH))
    try:
        response: dict[str, Any] | None
        for frame in iter_frames(sys.stdin.buffer):
            try:
                if frame is None:
                    response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Request exceeds limit"},
                    }
                else:
                    response = handle(parse_message(frame))
            except (ValueError, UnicodeDecodeError, RecursionError):
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            except Exception as exc:
                print(
                    f"OS29 MCP internal error: {type(exc).__name__}",
                    file=sys.stderr,
                    flush=True,
                )
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": "Internal error"},
                }
            if response is not None:
                sys.stdout.write(encode_response(response))
                sys.stdout.flush()
    finally:
        log_shutdown()


if __name__ == "__main__":
    main()
