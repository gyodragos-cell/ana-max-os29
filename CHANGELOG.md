# Changelog

## Unreleased — clean OS29 Core proposal

- Curated portable OS29 core and WorkUnitService code.
- MCP STDIO and CLI with generic local configuration defaults.
- Optional OS28 provider interface with deterministic offline mock.
- Local privacy scanner, CI, automated tests and isolated smoke.
- Security boundary and documentation; no private runtime data shipped.
- Public Git history intentionally left intact.

## Standalone wheel fix

- Bundle the existing default scope policy unchanged in the installable package.
- Verify CLI and MCP decisions from a fresh offline wheel installation outside the source tree.

## Release candidate validation

- Isolated release preview workflow from production Pages.
- Replaced unreviewed images with synthetic diagrams and kept strict privacy checks.
- Three-process handoff demo executes real regression commands and records receipts.
- Added site, workflow and README contract regressions.
- Documented benchmark scope and comparable top-five ranking metrics.
