# Architecture

OS29 Core is a model-neutral Python library. The Store persists trace events,
mission capsules, incidents, capability observations and explicitly selected
documents in a user-controlled SQLite database. WorkUnitService builds on the
same mission and trace records to provide work-unit creation, checkpoints,
evidence receipts, handoff and resume by ID.

Local retrieval uses SQLite FTS5/BM25. This is lexical search, not vector RAG
or autonomous reasoning. An agent must verify claims against evidence.

The optional os29.mcp_stdio exposes selected functions through MCP STDIO.
There is also an explicit CLI and optional HTTP gateway. Importing the Python
package does not launch an AI model, browser, live gateway or remote server.

OS28 is an independent local tool-infrastructure concept. The only public OS28
code in this branch is the protocol-shaped ToolProvider interface and
MockOS28Provider. No PC-specific implementation or credentials are embedded.
