# Contributing

Create a topic branch and send a pull request with reproducible tests.
Do not include private data, real tokens, passwords, screenshots, databases,
machine paths, historical personal files or local tool configurations.

Run before submitting:

    python scripts/privacy_gate.py
    python -m compileall -q os29 integrations examples scripts tests
    python -m pytest -q
    python scripts/offline_smoke.py
    git diff --check

Claims about new features must be supported by test commands and output.
Keep the local memory database outside the repository.
