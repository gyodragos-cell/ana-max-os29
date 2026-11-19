# Public release boundary

Only a manually selected allowlist is included: OS29 Python modules, matching
tests, generic examples, optional OS28 interface/mock, CI and documentation.

Excluded from publication: real .env files; passwords, tokens and keys;
private SQLite databases and WAL/SHM files; saved user memory; screenshots;
browser profiles; user documents; runtime logs and artifacts; caches, venv,
node_modules, desktop launchers and machine-specific configurations.

The canonical database of an existing private installation remains wherever
that operator has kept it. GitHub is NOT a backup of any user database.
No migration or automatic upload is performed.

Optional OS28 interface contracts are not the OS28 implementation; a user
supplies their own provider and configuration. This branch does not claim live
OS28 integration, measured tool counts, agent reasoning or enterprise
certification.

History: this proposal descends from public main. Its clean file tree does
not remove data from older Git objects. Any real historical secret requires
a separate rotation and incident decision without automatic rewriting.
