# OS29 Core

**Local evidence, memory and continuity for AI agents — not another AI model.**

[![CI](https://github.com/gyodragos-cell/ana-max-os29/actions/workflows/ci.yml/badge.svg?branch=release%2Fos28-os29-clean)](https://github.com/gyodragos-cell/ana-max-os29/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Site](https://img.shields.io/badge/Site-GitHub%20Pages-blue)](https://gyodragos-cell.github.io/ana-max-os29/)

OS29 is a Python library and MCP-compatible local service for storing evidence,
finding prior observations and handing work units between agent sessions. It
does not itself reason, host a language model or promise autonomous decisions.

OS28 is a **separate tool-infrastructure layer**. The public
`integrations/os28` package is only a portable interface and a deterministic
offline mock. It does not contain proprietary or machine-specific OS28 runtime tools.

## The problem

AI clients routinely lose context, repeat diagnostics and confuse observations
with verified results. OS29 supplies a local record of what was done, where the
evidence lives, what is still uncertain and the next safe action.

## Quick start

Requires Python 3.11 or newer.

```bash
git clone --branch release/os28-os29-clean https://github.com/gyodragos-cell/ana-max-os29.git
cd ana-max-os29
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -e ".[test]"
# Linux/macOS:
.venv/bin/python -m pip install -e ".[test]"

# Activate the virtual environment for your platform before these commands.
# Verify suite, privacy gate, and offline smoke
python -m pytest -q
python scripts/privacy_gate.py
python scripts/offline_smoke.py
python -m os29.cli --help
```

## CLI commands

Verified subcommands exposed by `python -m os29.cli`:

- `status`, `verify <work_id> [--expected-head SHA256]`, `demo`
- `trace`, `ingest-jsonl`, `capsule`, `snapshot`, `scope-check`
- `session` (`save`, `close`, `get`, `list`, `resume`, `import`)
- `memory-index`, `memory-search`, `memory-answer`
- `intelligence`, `experience-search`, `experience-validate`, `capabilities`, `capability-edges`

## Reproducible benchmark

Run locally — deterministic, `seed=42`, `500` synthetic episodes, `100` queries:

```bash
python benchmarks/run_benchmark.py
```

The benchmark uses a fixed synthetic corpus; timings vary by machine. Compare Recall@5 and MRR@5 at the same cutoff. It does not measure model reasoning.

Full results: [`benchmarks/results.json`](benchmarks/results.json) · Report: [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)

## What is included

- SQLite WAL mode (`PRAGMA journal_mode=WAL`), `busy_timeout`, `foreign_keys=ON`.
- **Atomic transactions**: capsule state, trace event, and integrity record written together.
- **SHA-256 hash-chain** (`os29/integrity.py`): `python -m os29.cli verify <work_id>` verifies chain integrity offline.
- SQLite FTS5/BM25 lexical search (`os29/retrieval.py`) — zero external dependencies.
- Optional vector hybrid retrieval (`os29/retrieval_vector.py`) with row-wise L2 normalization and NaN/Inf/zero-vector guards.
- **Bounded MCP STDIO server** (`os29/mcp_stdio.py`, `os29/mcp_validation.py`, `os29/mcp_policy.py`) with allowlist/denylist, timeouts, payload bounds, and secret redaction.

## Runnable examples

```bash
python examples/01_quickstart_work_unit.py       # Store & Work Unit quickstart
python examples/02_crash_recovery_chaos.py       # 5-process os._exit crash + WAL recovery
python examples/03_mcp_server_client_e2e.py      # Live STDIO MCP + PolicyDenied enforcement
python examples/04_custom_retriever_hybrid.py    # FTS5 vs Hybrid L2 retrieval & vector guards
python examples/05_multiagent_handoff_demo.py  # Three fresh processes, real synthetic regression
```

The handoff demo uses synthetic roles, not three independent AI models. The hash chain verifies internal consistency; it does not authenticate actors or attest to a receipt's truth.

## Documentation

- [Site Preview](site/index.html) / [GitHub Pages](https://gyodragos-cell.github.io/ana-max-os29/)
- [Architecture](docs/ARCHITECTURE.md)
- [Protocol Spec](docs/PROTOCOL_SPEC.md)
- [Integrity & Hash-Chain](docs/INTEGRITY.md)
- [Benchmarks](docs/BENCHMARKS.md)
- [Security Boundary](docs/SECURITY_BOUNDARY.md)
- [Changelog](CHANGELOG.md)
- [Release readiness](PRODUCTION_READINESS_REPORT.md)
- [Core library repo](https://github.com/gyodragos-cell/ana-max-os29-core)
