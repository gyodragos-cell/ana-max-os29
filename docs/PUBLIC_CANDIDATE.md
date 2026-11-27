# Public hardening candidate — validation guide

Status: development candidate, not a production release. The original public
FTS5/BM25 default remains unchanged. No private OS28 integration is required.

## Reproduce the checks

From the repository root with its development dependencies installed:

    python -m pytest -q tests/test_work_unit_atomicity.py tests/test_work_unit_integrity.py tests/test_mcp_validation.py tests/test_mcp_policy.py tests/test_retrieval_vector.py tests/test_public_http_gateway.py
    python -m pytest -q --cov=os29 --cov-branch --cov-report=term
    python -m mypy --strict os29

See INTEGRITY.md for the Work Unit hash-chain verification contract. A chain is
not an agent signature; an independently retained trusted head is necessary
to detect wholesale replacement or truncation.

## MCP public provider

OS29_MCP_POLICY_FILE points to an operator-owned JSON policy file. The default
does not authorize free-form terminal execution. File operations require an
explicit workspace root. Configured command aliases map to fixed argument
vectors, not arbitrary shell expressions. Do not configure untrusted programs
or scripts. The dry-run and read-only modes are capability restrictions, not
a substitute for OS-level process isolation. File/output bounds and command
timeouts are not universal process-memory or process-tree limits.

The read-only mode searches the existing index without refreshing it, so its
results may be stale. Protocol validation bounds JSON frames and validates
tool argument schemas before dispatch. See tests/test_mcp_policy.py and
tests/test_mcp_validation.py for executable examples of the policy and wire
behavior.

## Optional retrieval

os29.retrieval_vector provides a pluggable vector interface and deterministic
token-hash features. These features are lexical, not a pretrained semantic
embedding model. It normalizes rows independently, rejects invalid vectors
and combines vector and FTS5 rankings. FTS5 remains the default. Reproduce the
numerical invariants and real SQLite integration with:

    python -m pytest -q tests/test_retrieval_vector.py

This guide does not assert a comparative speedup or production readiness.
A public benchmark, expanded coverage, CI and independent review are required
before publishing stronger claims.
