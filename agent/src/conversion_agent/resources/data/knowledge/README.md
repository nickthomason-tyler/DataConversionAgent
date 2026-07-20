# Knowledge base

This directory is the agent's retrieval corpus. Everything here is versioned
markdown — the repo history *is* the knowledge audit trail.

Seed content:

- `playbook/` — symlink-free copies of the conversion process docs (sync from
  `docs/data-conversion-process/` in CI, or move the docs here and link the
  other way; pick one canonical home).
- `decisions/` — sanitized past-project decisions, one file per decision,
  with client identifiers removed.

Conventions:

- One topic per file, headings per sub-topic — retrieval chunks on headings.
- Every decision file states: context, options considered, decision, why,
  and which projects it applied to.
- The agent cites `[source: <file> § <heading>]`; keep headings stable.
