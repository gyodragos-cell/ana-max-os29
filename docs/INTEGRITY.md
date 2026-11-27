# Work Unit integrity (development candidate)

Every newly created Work Unit transition and evidence receipt is persisted with a
SHA-256 chain entry in the same SQLite transaction. The entry binds the
Work Unit ID, sequence, event ID, previous entry hash, stored event payload
(including the redaction count), and a hash of the stored capsule envelope.
The state and event insertion roll back together if either write fails.

## Reproduce offline

From the repository root, with the test extra installed:

```sh
python -m pytest -q tests/test_work_unit_atomicity.py tests/test_work_unit_integrity.py
```

These tests use disposable SQLite files, inject write failures, abruptly exit
a worker before commit, exercise ten concurrent independent Python writers,
and verify detection of changed and removed journal records.

To inspect a newly created Work Unit in your own database:

```sh
python -m os29.cli --db example.db verify work-unit-id
```

The JSON result includes the number of chain entries and events, validity,
errors and the current head. Record the head independently at a trusted
checkpoint and later compare the same expected head:

```sh
python -m os29.cli --db example.db verify work-unit-id --expected-head SHA256_HEAD
```

Exit status 0 means the checked chain is internally consistent; 3 indicates
a failed integrity check; invalid CLI input is an error. If a legitimate
new entry was appended, an earlier head is not the current expected head.

## Limits and migration

- No historical record is silently retroactively sealed. A legacy Work Unit
  with pre-chain events is reported as unsealed or incomplete.
- SHA-256 does not authenticate an agent or attest that a reported test ran.
  The trustworthiness of the original receipt is a separate problem.
- Without a trusted external current-head anchor, an attacker with unrestricted
  write access can rewrite or truncate an entire internally consistent chain.
- Historical state hashes are linked, but historical capsule snapshots are
  not retained in this table. Only the current capsule can be recomputed.
- The checks are for Work Unit events; unrelated trace events are not covered.
- SQLite access permissions and backups remain operator responsibilities.
