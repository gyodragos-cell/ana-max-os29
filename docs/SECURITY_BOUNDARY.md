# Security boundary

This public project contains source code, fixtures and interface contracts;
it contains no user runtime state. Source selection is allowlist-based rather
than relying on .gitignore as the primary privacy control.

The installer controls its own local SQLite path. Redaction helpers and
scope checks do not replace an operating-system permissions policy. Optional
network/terminal integrations have their own risk profiles and should be
reviewed before use in production.

The current public repository has Git history prior to this clean release
branch. Deleting a tracked file in this branch does not erase its earlier
contents from existing commits. Report discovered historical credentials
privately and rotate them separately; no history rewriting is performed here.
