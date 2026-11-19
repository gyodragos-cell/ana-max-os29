"""Reject disallowed tracked files, machine paths and plausible hardcoded secrets."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED_FILES = [
    re.compile(r"(^|/)(?:data|logs?|artifacts?|screenshots?|browser[_-]?profiles?|node_modules|cache|\.cache|\.venv|venv|__pycache__)(/|$)", re.I),
    re.compile(r"(^|/)\.env($|\.)", re.I),
    re.compile(r"\.(?:db|sqlite|sqlite3)(?:-wal|-shm)?$", re.I),
    re.compile(r"\.(?:log|jsonl|pyc)$", re.I),
]
BANNED_PATH_VALUES = [
    re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+[A-Za-z0-9_.-]+"),
    re.compile(r"(?i)[A-Z]:[\\/]+OS28_MEMORY"),
    re.compile(r"\bPC1313\b", re.I),
]
POSSIBLE_SECRETS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"(?<![A-Za-z0-9_])(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}")),
    ("openai_key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{24,}")),
    ("aws_key", re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9])eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{8,}")),
    ("bearer", re.compile(r"(?im)^\s*(?:Authorization|Proxy-Authorization)\s*[:=]\s*(?:Bearer|Basic)\s+[A-Za-z0-9_+/=-]{12,}")),
    ("literal_credential", re.compile(
        r"""(?im)^\s*["']?(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|private[_-]?key)["']?\s*[:=]\s*["']?([A-Za-z0-9_.+/=-]{16,})"""
    )),
]

def main() -> int:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    names = [entry for entry in output.decode("utf-8").split("\x00") if entry]
    rejected: set[tuple[str, str]] = set()
    for name in names:
        rel = name.replace("\\", "/")
        if rel != ".env.example" and any(pattern.search(rel) for pattern in BANNED_FILES):
            rejected.add((rel, "disallowed_path"))
            continue
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            rejected.add((rel, "missing_or_symlink"))
            continue
        raw = path.read_bytes()
        if b"\x00" in raw:
            rejected.add((rel, "nontext_not_allowlisted"))
            continue
        content = raw.decode("utf-8-sig", errors="replace")
        for pattern in BANNED_PATH_VALUES:
            if pattern.search(content):
                rejected.add((rel, "private_machine_path"))
        for category, pattern in POSSIBLE_SECRETS:
            if pattern.search(content):
                rejected.add((rel, "possible_" + category))
    print(f"PRIVACY_SCAN tracked={len(names)} findings={len(rejected)}")
    for rel, category in sorted(rejected):
        print("REJECT " + rel + " category=" + category)
    return 1 if rejected else 0

if __name__ == "__main__":
    sys.exit(main())
