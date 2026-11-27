# Public protocol specification

## Work Unit V1

The public `WorkUnitService` stores a versioned capsule and records trace
events in SQLite. Create a unit using a unique work ID and owner; checkpoint
updates require the expected revision. Handoff transfers ownership to the
next role. Resume retrieves the persisted state, latest receipt and context
pack by work ID. Statuses: active, handoff_ready, completed, blocked.
Completion requires a persisted successful executable-test receipt.
See `os29/work_units.py` and the runnable examples for exact arguments.

## Integrity

New Work Unit events are committed with SHA-256 chain entries. The chain
binds the stored event and capsule state to its predecessor. Verify with
`python -m os29.cli --db example.db verify work-unit-id`; optionally pass
`--expected-head` with an independently retained SHA-256 head.
See [integrity and limits](INTEGRITY.md). Internal consistency does not
authenticate the original actor or prove the truth of a receipt.

## MCP STDIO

Run `python -m os29.mcp_stdio`. The provider implements newline-delimited
UTF-8 JSON-RPC 2.0 (protocol version 2024-11-05). Initialize before calling
`tools/list` and `tools/call`. Tool schemas are discovered at runtime.
The implementation rejects duplicate keys and non-finite JSON values; frame
and output limits are 1,048,576 bytes, depth 32, and node count 50,000.
Configuration and policies are described in [Security boundary](SECURITY_BOUNDARY.md).
Run `python examples/03_mcp_server_client_e2e.py` to exercise the wire
protocol, a real receipt and negative policy cases without external services.

## Handoff demo

`python examples/05_multiagent_handoff_demo.py` starts three separate
synthetic role processes with a disposable database and fixture. The first
process runs a failing test and repairs the fixture; subsequent processes
recover the work ID, verify file hashes, and run the regression independently.
This demonstrates process isolation and continuity, not reasoning by three
independent AI models.
