# ANA MAX OS29
## Explore the public Tower Control V2

**[Open the interactive Tower](https://gyodragos-cell.github.io/ana-max-os29/live.html)** · **[OS28 tool examples](https://gyodragos-cell.github.io/ana-max-os29/live.html#services)** · **[Two AI agents, one real bug](https://gyodragos-cell.github.io/ana-max-os29/wow.html)**

The English public edition reproduces the local Tower design. Explore eleven views, simulated services, a sample mission handoff, and historical screenshots and repair evidence. The browser demo uses synthetic state only: no live machine connection, private database, or remote execution. The local OS28 tool catalog is not bundled with the public OS29 Core.

## For everyone: what OS29 actually does

**Imagine an AI spends an hour investigating a problem, but the conversation ends.**
A second AI should be able to see **what happened, what failed, what worked, and
what still needs fixing** — without starting the investigation from scratch.

That is the purpose of OS29: **a local notebook for AI work, with proof**.
It is not another chatbot or a guarantee of bug-free software.

**[See how it works in 60 seconds — English or Romanian](https://gyodragos-cell.github.io/ana-max-os29/start-here.html)**

In a real private lab test, Qwen 7B produced a *partial* code repair and GPT-6
corrected one expression. The combined fix passed regression checks. The
public site explains that distinction instead of claiming perfect autonomy.

**Want to help?** [Try the public reproducible example](https://github.com/gyodragos-cell/ana-max-os29-core/blob/main/examples/cosine_red_green_demo.py),
[report a bug](https://github.com/gyodragos-cell/ana-max-os29/issues), or
[leave a GitHub star](https://github.com/gyodragos-cell/ana-max-os29)
if you find the idea useful.

---

## Operational Intelligence · Local-First · Evidence-Driven

OS29 is a local-first operational-intelligence layer for traceable diagnostics, bounded tools and evidence-linked memory. It is designed to make system observations inspectable and to keep the difference between **declared**, **configured**, **running**, **tested**, **degraded** and **unknown** capabilities explicit.

This repository is the clean OS29 source tree. It does not include the historical OS27/OS28 workspace, browser profiles, local runtime databases, private memory sources, cache trees, local logs or machine-specific MCP client configuration. Optional OS28 adapters are kept at the integration boundary; the OS28 implementation itself is not bundled here.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![OS29 local baseline](https://img.shields.io/badge/OS29%20local%20baseline-37%20passed-2e8b57.svg)](docs/VERIFICATION.md)
[![Portfolio](https://img.shields.io/badge/Portfolio-GitHub%20Pages-5468ff.svg)](https://gyodragos-cell.github.io/ana-max-os29/)

## Latest verified OS29 Core: see the difference

**The portable OS29 Core now has a reproducible before/after memory demo.**
The historical metrics farther down this README describe an earlier snapshot
of this separate portfolio repository; they are not the current Core test count.

| Reproducible public demonstration | Earlier behavior | Verified OS29 Core |
|---|---|---|
| Legacy trace JSON missing embedded event ID | **0** entries eligible for indexing | **1** entry retrieved using the SQLite primary key |
| Stored original trace JSON | Not recovered by retrieval | **Unchanged** |
| Automated public release checks | Historical portfolio snapshot | **112 tests passed** locally; Windows, Ubuntu and Gitleaks GitHub CI **PASS** |

**[Explore the current Core source](https://github.com/gyodragos-cell/ana-max-os29-core)** ·
**[See the before/after walkthrough](https://github.com/gyodragos-cell/ana-max-os29-core/blob/main/docs/SEE_THE_DIFFERENCE.md)** ·
**[Run the actual example](https://github.com/gyodragos-cell/ana-max-os29-core/blob/main/examples/see_the_difference.py)**

The Core documentation also reports bounded **private local research** comparing
FTS5 and multilingual semantic retrieval. Those sample measurements are
**not a publicly reproducible benchmark or a shipped semantic-search feature**.
The current Core runtime still uses lexical FTS5/BM25. No user data,
model weights or operator databases are published.

## What is included

- **Trace contract:** normalized events with stable IDs, parent lineage, timestamps and explicit outcomes.
- **Redaction and bounded persistence:** sensitive-value masking, URL normalization and size limits before SQLite storage.
- **Scope enforcement:** local-first host/port policy and exact device/process allowlists for optional Frida hooks.
- **Evidence-linked diagnosis:** incidents and hypotheses preserve their source references; correlation is not presented as proven causation.
- **Mission capsules and experiences:** candidate and validated experience states remain distinct; validation is an explicit local operator action.
- **Capability map:** declared/configured/running/tested/degraded/offline/unknown states with evidence timestamps.
- **Memory retrieval:** SQLite FTS5/BM25 over selected local evidence; lexical retrieval only, not semantic/vector RAG.
- **MCP STDIO:** bounded local tool surface for observing and retrieving evidence.
- **Optional HTTP API:** bearer-protected and loopback-bound; it is not started automatically.

## Architecture at a glance

```text
Local observations / approved adapters
                 |
                 v
        os29.trace.v1 + redaction
                 |
                 v
      SQLite events / incidents / capsules
                 |
                 +------> Capability graph
                 |
                 +------> FTS5 / BM25 retrieval
                 |
                 v
       CLI + bounded MCP STDIO tools
                 |
                 v
     Evidence review / candidate experience
                 |
                 v
       Explicit local validation action
```

Read [the architecture](docs/ARCHITECTURE.md), [security model](docs/SECURITY_MODEL.md), [retrieval semantics](docs/MEMORY_RETRIEVAL.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md) for the boundaries and open acceptance gates.

## Quick start

Python 3.11+ is required. Use an isolated environment; the core has no mandatory third-party runtime dependencies.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m os29.cli status
python -m os29.cli snapshot
python -m os29.cli intelligence
python -m os29.cli memory-index
python -m os29.cli memory-search "gateway" --limit 10
python -m pytest -q
node --check .\integrations\frida\os29_trace.js
```

The default store path is local under `data/`; set `OS29_DB_PATH` and `OS29_SCOPE_PATH` to explicit paths when needed. Runtime databases, logs and generated artifacts are intentionally ignored by Git.

## MCP STDIO

Run the local companion from the repository root:

```powershell
python -m os29.mcp_stdio
```

A compatible local MCP client can launch this process with the example in [config/OS29_MCP_CLIENT_CONFIG.example.json](config/OS29_MCP_CLIENT_CONFIG.example.json) after replacing its path placeholders. The public website does not connect to the visitor's machine and does not register this local MCP server in ChatGPT automatically.

## Optional HTTP gateway

The HTTP API is separate from STDIO and is not started by default. It binds to loopback and refuses startup without a sufficiently long `OS29_GATEWAY_TOKEN`. Keep the endpoint private; loopback binding is not a substitute for per-operation authorization or an OS-level sandbox.

## Recorded local baseline

The local checkpoint dated **19 October 2026** recorded **37 passing tests**, **14 MCP STDIO tools**, and **375 lexical-index documents**. The checkpoint had **zero validated experiences**; candidate records are not promoted automatically. These are historical local measurements, not live counters or claims that all roadmap modules are complete. See [Verification](docs/VERIFICATION.md) and [Implementation status](docs/IMPLEMENTATION_STATUS.md).

## Project limits — stated plainly

- Retrieval is SQLite FTS5/BM25. Semantic embeddings, reranking and a model-mediated reasoning loop are not implemented.
- No real authorized Android/USB target was connected in the recorded baseline; no real app hook or Frida-to-MITM correlation is claimed.
- A measured, real fix/retest and a validated lesson retrieved in a later session remain acceptance gates.
- SQLite is not encrypted at rest. Redaction is defensive and is not a perfect secret/PII detector.
- The 30-module roadmap is a staged plan, not a statement that all modules are production-complete.

## Public portfolio

- [ANA MAX / OS29 portfolio](https://gyodragos-cell.github.io/ana-max-os29/)
- [Live Profile demo](https://gyodragos-cell.github.io/ana-max-os29/live.html)
- [Professional CV](https://gyodragos-cell.github.io/ana-max-os29/cv.html)

The static portfolio demonstrates the presentation layer only. It does not execute OS29 commands or inspect local runtime state.
