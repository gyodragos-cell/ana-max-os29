# Clean-clone quick start

Requirements: Python 3.11+ and Git.

1. Clone the repository and checkout release/os28-os29-clean.
2. Create a Python venv: python -m venv .venv
3. Install: python -m pip install -e ".[test]"
4. Compile: python -m compileall -q os29 integrations examples scripts tests
5. Test: python -m pytest -q
6. Offline smoke: python scripts/offline_smoke.py
7. Privacy scan: python scripts/privacy_gate.py

Python under .venv should be used after creating the environment. The sample
smoke creates an SQLite file in a temporary directory only. No private storage,
Windows drive layout, third-party gateway or Ollama server is needed.

For MCP clients, adapt examples/mcp_client.example.json with your OWN local
paths. The .env.example is reference material only: it is not automatically
loaded. Do not point test tools at a database containing private memory.
