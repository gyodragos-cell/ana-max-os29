# OS29 Core

**Local evidence, memory and continuity for AI agents — not another AI model.**

OS29 is a Python library and MCP-compatible local service for storing evidence,
finding prior observations and handing work units between agent sessions. It
does not itself reason, host a language model or promise autonomous decisions.

OS28 is a **separate tool-infrastructure layer**. The public
integrations/os28 package is only a portable interface and a deterministic
offline mock. It does not contain the proprietary or private local OS28
implementation. Connecting an actual tool provider is optional.

## The problem

AI clients routinely lose context, repeat diagnostics and confuse observations
with verified results. OS29 supplies a local record of what was done, where the
evidence lives, what is still uncertain and the next safe action. The actual
agent decides what to do with it.

## What is included

- SQLite-backed traces, mission capsules, work units and evidence receipts.
- Checkpoints, handoff and resume by Work Unit ID using the same local store.
- SQLite FTS5/BM25 **lexical** search, not vector or semantic AI reasoning.
- Optional MCP STDIO provider, CLI and separately started HTTP gateway.
- Portable OS28 provider contract, offline mock, tests and privacy checks.
- No preloaded model, memory, database, real credentials or private logs.

## Architecture

    Operator-selected AI client / local model
                    |
             MCP STDIO / Python
                    |
             OS29 Core library
          evidence | Work Units | search
                    |
              local SQLite
                    |
       Optional OS28 provider interface
            (user-configured, mock by default)

## Quick start

Requires Python 3.11 or newer.

    git clone https://github.com/gyodragos-cell/ana-max-os29.git
    cd ana-max-os29
    python -m venv .venv
    python -m pip install -e ".[test]"
    python -m compileall -q os29 integrations examples scripts tests
    python -m pytest -q
    python scripts/privacy_gate.py
    python scripts/offline_smoke.py
    python -m os29.cli --help

For the proposed clean release, checkout branch release/os28-os29-clean
before installing. On Windows, invoke the Python interpreter under
.venv/Scripts; on Linux and macOS use .venv/bin.

The smoke test creates an isolated **temporary** SQLite database and removes it
afterwards. The application does not need an existing private store, a lab
computer, a gateway service or a network connection for these basic tests.
Installing dependencies initially may require a package index.

## Conceptual workflow

1. Agent A creates a Work Unit with a project, objective and next action.
2. Agent A records evidence and a checkpoint in a user-selected local database.
3. Agent B opens that same database and resumes with only the Work Unit ID.
4. Agent B independently verifies evidence before marking a task completed.

The offline smoke proves persistence and resume across separate Store objects.
It does **not** imply that two actual AI models executed the workflow.

## Known limitations

- Work units are persisted context, not proof that a task is correct.
- FTS5 search is lexical and depends on the local SQLite build.
- Multi-machine replication and enterprise multi-user access are not shipped.
- Optional network tools require operator-provided configuration and review.
- No local AI inference engine, semantic embeddings, Frida or live OS28 gateway
  are included.
- This branch does not erase historic content from the public main Git history.
- Documentation describes a developer preview, not a certified institution
  deployment or a measured performance advantage.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Offline quick start](docs/QUICK_START.md)
- [Security boundary](docs/SECURITY_BOUNDARY.md)
- [Roadmap](docs/ROADMAP.md)
- [Public release boundary](PUBLIC_RELEASE_BOUNDARY.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

MIT license: [LICENSE](LICENSE).
