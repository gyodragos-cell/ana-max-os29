# OS29 release candidate — evidence and limits

## Scope

Portable Python package and local MCP STDIO service, on the
`release/os28-os29-clean` branch of `ana-max-os29`. This is a release
candidate, not a guarantee of production readiness or absence of defects.
The private OS28 runtime and operational memory are not shipped.

## Reproduce

Clone the candidate branch, create a fresh virtual environment, activate it,
then install the development extra:

```sh
git clone --branch release/os28-os29-clean https://github.com/gyodragos-cell/ana-max-os29.git
cd ana-max-os29
python -m venv .venv
# Activate .venv using the instructions for your platform.
python -m pip install -e ".[dev]"
python scripts/privacy_gate.py
python -m ruff check os29 tests examples benchmarks
python -m ruff format --check os29 tests examples benchmarks
python -m mypy os29
python -m pytest -q --cov=os29 --cov-fail-under=90
python -m compileall -q os29 integrations examples scripts tests
python scripts/offline_smoke.py
python examples/01_quickstart_work_unit.py
python examples/02_crash_recovery_chaos.py
python examples/03_mcp_server_client_e2e.py
python examples/04_custom_retriever_hybrid.py
python examples/05_multiagent_handoff_demo.py
python benchmarks/run_benchmark.py
```

The runtime itself does not require a cloud backend. Installing build and
test dependencies may require package downloads or a prepared local wheelhouse.

## Verification gates

CI results are attached to the exact commit in GitHub Actions. The matrix
covers Windows and Linux with Python 3.11 and 3.12. The release preview is
validated and archived, and never deployed over the main portfolio. Test and
coverage failures are release blockers; the coverage threshold is 90%.

The privacy gate scans tracked filenames, text contents and patterns for
plausible secrets and private paths. It is not proof of absence of all secrets.
Unreviewed binary images are excluded from this candidate. No database or
private machine screenshots are needed to reproduce the release.

## Demonstration

Example 05 uses three separate Python subprocesses as synthetic roles.
Role A reproduces a failing fixture test, patches the fixture and reruns
the test; roles B and C recover the persisted work ID and rerun the test.
The demo verifies actual exit codes and fixture hashes. It does not execute
three independent language models, nor does it patch an OS28 private tool.
The hash chain proves internal consistency, not authentication or the truth
of arbitrary receipts. Retain an independent expected head for tamper checks.

## Benchmarks

See [recorded results](benchmarks/results.json) and
[benchmark documentation](docs/BENCHMARKS.md). The fixed synthetic corpus
measures lexical retrieval latency, Recall@5 and MRR@5; timing varies by
hardware. No superiority over other products is asserted.

## Independent local validation (2026-11-27)

On Windows with Python 3.12 in a fresh development virtual environment:
357 tests passed, 92.33% statement coverage, Ruff lint and format passed,
strict mypy passed (30 source files), all five examples and offline smoke
exited zero, privacy gate returned zero findings for 105 tracked files,
and the Git whitespace checks passed. The synthetic three-process demo
recorded nine valid chain entries and four receipts. These are measured
candidate results, not a substitute for the hosted matrix.

## Remaining acceptance criteria

- Independent live handoff between three real AI models is not proven by the
  portable demo.
- A dedicated, independently validated 30-case verified operational replay
  benchmark and measured model-independent replay refusal rate are not
  established by the lexical retrieval benchmark.
- Existing private lab databases are not automatically migrated by this
  public candidate; use a disposable database when running examples.
- External secret audit, operational soak testing, backup/restore drills and
  production deployment validation remain separate from unit test success.

**Verdict: RELEASE_CANDIDATE.** The exact CI matrix and independent operational
acceptance results determine subsequent promotion.
