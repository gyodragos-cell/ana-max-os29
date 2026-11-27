"""Operator-configured capability policy for the public MCP provider.

This is a tool-level boundary, not an OS sandbox. Only trusted operators may
configure the workspace and exact executable argument vectors.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

READ_ONLY_TOOLS = frozenset(
    {
        "os29_status",
        "os29_trace_get",
        "os29_capabilities_list",
        "os29_capability_edges_list",
        "os29_mission_capsule_get",
        "os29_work_unit_get",
        "os29_work_unit_list",
        "os29_work_unit_resume",
        "os29_work_unit_receipt",
        "os29_work_unit_verify",
        "os29_session_get",
        "os29_session_list",
        "os29_experience_search",
        "os29_memory_search",
        "tower_resume",
        "tower_memory_search",
        "os29_file_read",
        "os29_code_search",
    }
)
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", ".venv", "venv", "node_modules"}


class PolicyDenied(ValueError):
    """A non-sensitive reason suitable for the policy audit trail."""


def _string_set(value: Any, label: str) -> frozenset[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"invalid policy {label}")
    return frozenset(value)


def _integer(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid policy {label}")
    return value


@dataclass(frozen=True)
class CapabilityPolicy:
    mode: str = "normal"
    workspace_root: Path | None = None
    allow_tools: frozenset[str] | None = None
    deny_tools: frozenset[str] = frozenset()
    commands: dict[str, tuple[str, ...]] = field(default_factory=dict)
    max_timeout_seconds: int = 30
    max_file_bytes: int = 262_144
    max_output_bytes: int = 262_144

    @classmethod
    def from_environment(cls) -> CapabilityPolicy:
        path = os.environ.get("OS29_MCP_POLICY_FILE")
        if not path:
            return cls()
        with Path(path).open("rb") as stream:
            raw = stream.read(65_537)
        if len(raw) > 65_536:
            raise ValueError("MCP policy file exceeds size limit")
        data = json.loads(raw.decode("utf-8"))
        allowed = {
            "mode",
            "workspace_root",
            "allow_tools",
            "deny_tools",
            "commands",
            "max_timeout_seconds",
            "max_file_bytes",
            "max_output_bytes",
        }
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError("invalid MCP policy fields")
        mode = data.get("mode", "normal")
        if mode not in {"normal", "read-only", "dry-run"}:
            raise ValueError("invalid MCP policy mode")
        raw_root = data.get("workspace_root")
        root = None
        if raw_root is not None:
            if not isinstance(raw_root, str) or not Path(raw_root).is_absolute():
                raise ValueError("workspace root must be an absolute path")
            root = Path(raw_root).resolve()
            if not root.is_dir():
                raise ValueError("workspace root must be an existing directory")
        raw_commands = data.get("commands", {})
        commands: dict[str, tuple[str, ...]] = {}
        if not isinstance(raw_commands, dict):
            raise ValueError("invalid command policy")
        for alias, argv in raw_commands.items():
            if (
                not isinstance(alias, str)
                or not alias
                or len(alias) > 128
                or not isinstance(argv, list)
                or not argv
                or len(argv) > 64
                or any(
                    not isinstance(arg, str) or "\x00" in arg or len(arg) > 4096
                    for arg in argv
                )
            ):
                raise ValueError("invalid command alias or argument vector")
            executable = Path(argv[0])
            if (
                not executable.is_absolute()
                or not executable.is_file()
                or executable.suffix.lower() in {".cmd", ".bat", ".ps1"}
            ):
                raise ValueError(
                    "approved executable must be an absolute executable file"
                )
            commands[alias] = tuple(argv)
        return cls(
            mode=mode,
            workspace_root=root,
            allow_tools=_string_set(data["allow_tools"], "allow_tools")
            if "allow_tools" in data
            else None,
            deny_tools=_string_set(data.get("deny_tools", []), "deny_tools"),
            commands=commands,
            max_timeout_seconds=_integer(
                data.get("max_timeout_seconds", 30), "timeout", 1, 90
            ),
            max_file_bytes=_integer(
                data.get("max_file_bytes", 262_144), "file size", 1, 1_048_576
            ),
            max_output_bytes=_integer(
                data.get("max_output_bytes", 262_144), "output size", 1024, 1_048_576
            ),
        )

    def resolve_path(self, value: str | None) -> Path:
        if self.workspace_root is None:
            raise PolicyDenied("workspace_not_configured")
        root = self.workspace_root
        path = Path(value) if value is not None else root
        try:
            resolved = (path if path.is_absolute() else root / path).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise PolicyDenied("invalid_workspace_path") from exc
        if not resolved.is_relative_to(root):
            raise PolicyDenied("path_outside_workspace")
        return resolved

    def prepare(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name in self.deny_tools or (
            self.allow_tools is not None and name not in self.allow_tools
        ):
            raise PolicyDenied("tool_not_allowed")
        if self.mode == "read-only" and name not in READ_ONLY_TOOLS:
            raise PolicyDenied("read_only_policy")
        result = dict(args)
        if name in {"os29_file_read", "os29_file_write"}:
            target = self.resolve_path(args["path"])
            result["path"] = str(target)
            if name == "os29_file_read":
                if not target.is_file():
                    raise PolicyDenied("file_not_found")
                if target.stat().st_size > self.max_file_bytes:
                    raise PolicyDenied("file_size_limit")
            elif len(args["content"].encode("utf-8")) > self.max_file_bytes:
                raise PolicyDenied("file_size_limit")
        elif name == "os29_code_search":
            root = self.resolve_path(args.get("search_path"))
            if not root.is_dir():
                raise PolicyDenied("search_directory_not_found")
            if not args["pattern"] or len(args["pattern"]) > 512:
                raise PolicyDenied("search_pattern_limit")
            if args.get("max_results", 50) > 100:
                raise PolicyDenied("search_result_limit")
            result["search_path"] = str(root)
        elif name == "os29_terminal_exec":
            if args["command"] not in self.commands:
                raise PolicyDenied("command_alias_not_approved")
            cwd = self.resolve_path(args.get("cwd"))
            if not cwd.is_dir():
                raise PolicyDenied("command_directory_not_found")
            timeout = args.get("timeout_seconds", min(30, self.max_timeout_seconds))
            if timeout > self.max_timeout_seconds:
                raise PolicyDenied("command_timeout_limit")
            result["cwd"] = str(cwd)
            result["timeout_seconds"] = timeout
        elif (
            name == "os29_memory_answer"
            and args.get("timeout_seconds", 45) > self.max_timeout_seconds
        ):
            # Keep the default model timeout compatible, but constrain explicit policy overrides.
            if "timeout_seconds" in args:
                raise PolicyDenied("model_timeout_limit")
            result["timeout_seconds"] = self.max_timeout_seconds
        return result


def bounded_file_read(
    path: str, limit: int, start_line: int | None = None, end_line: int | None = None
) -> dict[str, Any]:
    target = Path(path)
    with target.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise PolicyDenied("file_size_limit")
    lines = raw.decode("utf-8", errors="replace").splitlines()
    start = max(1, start_line or 1)
    end = min(len(lines), end_line if end_line is not None else len(lines))
    return {
        "path": str(target),
        "total_lines": len(lines),
        "start_line": start,
        "end_line": end,
        "content": "\n".join(lines[start - 1 : end]),
    }


def bounded_literal_search(
    path: str,
    pattern: str,
    *,
    max_results: int,
    case_sensitive: bool,
    policy: CapabilityPolicy,
) -> dict[str, Any]:
    root = Path(path)
    matches: list[dict[str, Any]] = []
    needle = pattern if case_sensitive else pattern.casefold()
    deadline = time.monotonic() + policy.max_timeout_seconds
    scanned = total = 0
    truncated = False
    for directory, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(item for item in directories if item not in SKIP_DIRS)
        for filename in sorted(files):
            if (
                scanned >= 1000
                or total >= 8_388_608
                or time.monotonic() >= deadline
                or len(matches) >= max_results
            ):
                truncated = True
                break
            target = Path(directory) / filename
            if target.is_symlink() or not target.resolve().is_relative_to(root):
                continue
            scanned += 1
            try:
                with target.open("rb") as stream:
                    raw = stream.read(min(policy.max_file_bytes, 8_388_608 - total) + 1)
                total += len(raw)
                if len(raw) > policy.max_file_bytes or total > 8_388_608:
                    truncated = True
                    continue
                for number, line in enumerate(
                    raw.decode("utf-8", errors="replace").splitlines(), 1
                ):
                    if time.monotonic() >= deadline:
                        truncated = True
                        break
                    text = line if case_sensitive else line.casefold()
                    if needle in text:
                        matches.append(
                            {
                                "file": str(target),
                                "line": number,
                                "text": line[:250].strip(),
                            }
                        )
                        if len(matches) >= max_results:
                            truncated = True
                            break
            except OSError:
                continue
        if truncated and (
            len(matches) >= max_results
            or scanned >= 1000
            or total >= 8_388_608
            or time.monotonic() >= deadline
        ):
            break
    return {
        "pattern": pattern,
        "search_path": str(root),
        "match_count": len(matches),
        "matches": matches,
        "files_scanned": scanned,
        "bytes_scanned": total,
        "truncated": truncated,
    }


def bounded_command(
    argv: tuple[str, ...], cwd: str, timeout: int, max_output: int
) -> dict[str, Any]:
    """Execute only trusted argv, no shell, with bounded RAM and wall time."""
    started = time.monotonic()
    env = {
        name: os.environ[name]
        for name in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        if name in os.environ
    }
    reason = ""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        with subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        ) as process:
            while process.poll() is None:
                if (
                    os.fstat(stdout.fileno()).st_size
                    + os.fstat(stderr.fileno()).st_size
                    > max_output
                ):
                    reason = "command_output_limit"
                    break
                if time.monotonic() - started >= timeout:
                    reason = "command_timeout"
                    break
                time.sleep(0.01)
            if reason and process.poll() is None:
                process.kill()
            code = process.wait(timeout=5)
        if (
            os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size
            > max_output
        ):
            reason = reason or "command_output_limit"
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(max_output)
        err = stderr.read(max_output - len(out))
    return {
        "exit_code": -1 if reason else code,
        "stdout": out.decode("utf-8", errors="replace"),
        "stderr": err.decode("utf-8", errors="replace"),
        "reason": reason or None,
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
    }
