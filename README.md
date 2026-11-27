# OS29 Core

**Local evidence, memory and continuity for AI agents — not another AI model.**

[![CI](https://github.com/gyodragos-cell/ana-max-os29/actions/workflows/ci.yml/badge.svg)](https://github.com/gyodragos-cell/ana-max-os29/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Site](https://img.shields.io/badge/Site-GitHub%20Pages-blue)](https://gyodragos-cell.github.io/ana-max-os29/)

OS29 is a Python library and MCP-compatible local service for storing evidence,
finding prior observations and handing work units between agent sessions. It
does not itself reason, host a language model or promise autonomous decisions.

OS28 is a **separate tool-infrastructure layer**. The public
`integrations/os28` package is only a portable interface and a deterministic
offline mock. It does not contain the proprietary or private local OS28
implementation. Connecting an actual tool provider is optional.

## The problem

AI clients routinely lose context, repeat diagnostics and confuse observations
with verified results. OS29 supplies a local record of what was done, where the
evidence lives, what is still uncertain and the next safe action. The actual
agent decides what to do with it.

## Quick start

Requires Python 3.11 or newer.

```bash
git clone https://github.com/gyodragos-cell/ana-max-os29.git
cd ana-max-os29
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -e ".[test]"
# Linux/macOS:
.venv/bin/python -m pip install -e ".[test]"

# Run all tests
python -m pytest -q

# Try the CLI
python -m os29.cli --help
python -m os29.cli verify --help
```

## Reproducible benchmark

Run locally — deterministic, seed=42, 500 episodes:

```bash
python benchmarks/run_benchmark.py
```

| Strategy | p50 (ms) | p95 (ms) | p99 (ms) | Recall@5 | MRR |
|---|---|---|---|---|---|
| Baseline 1 — Python dict + LIKE | 0.0924 | 0.0961 | 0.1377 | 70.0% | 0.3655 |
| Baseline 2 — Regex full-scan | 0.3905 | 0.7153 | 0.9636 | 70.0% | 0.3655 |
| **OS29 FTS5/BM25 + WAL** | **0.0613** | **0.0918** | **0.1973** | **70.0%** | 0.3197 |

Full results: [`benchmarks/results.json`](benchmarks/results.json) · Report: [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)

## What is included

- SQLite WAL mode, busy_timeout=10000ms, foreign keys — multi-process safe.
- **SHA-256 hash-chain**: `os29 verify <work_unit_id>` confirms cryptographic integrity.
- **Atomic transactions**: state + evidence in one write — no orphaned state on crash.
- SQLite FTS5/BM25 lexical search — zero external dependencies.
- Optional vector retrieval with row-wise L2 normalization (NumPy).
- **MCP STDIO provider** with policy guard: allowlist/denylist, timeouts, secret redaction.
- CLI: `os29 verify`, `os29 doctor`, `os29 bench`, `os29 demo`.
- Examples: quickstart, crash recovery chaos, MCP e2e, hybrid retrieval.

## Architecture

```
Operator-selected AI client / local model
                |
         MCP STDIO / Python import
                |
         OS29 Core library
   Policy Guard | MCP Validation
   Work Units | Evidence | FTS5 Search
   Checkpoint | Hash-Chain | WAL
                |
          local SQLite file
                |
   Optional OS28 provider interface
        (offline mock by default)
```

## Verify integrity

```bash
python -m os29.cli verify <work_unit_id>
```

Returns `{"valid": true, "hash": "sha256:..."}` or lists broken links in the chain.

## Examples

```bash
python examples/01_quickstart_work_unit.py    # Full Work Unit lifecycle
python examples/02_crash_recovery_chaos.py    # 5-process crash + recovery
```

## Security

See [docs/SECURITY_BOUNDARY.md](docs/SECURITY_BOUNDARY.md). The MCP policy guard
enforces allowlist/denylist per tool, strict per-call timeouts and automatic
secret redaction. No credentials, tokens or private memory are stored in SQLite
without explicit whitelisting.

## Links

- [Site](https://gyodragos-cell.github.io/ana-max-os29/) — live demo page with real screenshots
- [Architecture](docs/ARCHITECTURE.md)
- [Benchmarks](docs/BENCHMARKS.md)
- [Security Boundary](docs/SECURITY_BOUNDARY.md)
- [Changelog](CHANGELOG.md)
- [Core library repo](https://github.com/gyodragos-cell/ana-max-os29-core)
