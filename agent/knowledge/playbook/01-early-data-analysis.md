# Pillar 1 — Early Legacy Data Analysis

Goal: within the first 2–3 weeks of a project, produce a data-driven picture of the client's current state that (a) accelerates and de-risks Assess & Define documentation and (b) tells the implementation team what will need to be configured — before configuration workshops begin.

## Step 1: Secure data access at kickoff (week 0–1)

Make data access a **contractual kickoff deliverable**. Include in the SOW/kickoff checklist:

- Signed data processing agreement and security review (encryption in transit/at rest, retention, PII handling).
- One of the following access paths, in order of preference:
  1. **Client-run extraction package** — you ship parameterized extract scripts (SQL Server and Oracle variants); the client runs them and delivers flat files/backups to your secure transfer point. Lowest friction with client security teams.
  2. **Read-only replica or backup restore** into your conversion environment.
  3. **Direct read-only connection** (VPN + read-only credentials) — fastest iteration but hardest to get approved.
- A named **Client Data Steward** who can answer "what does this column mean" questions with a 48-hour SLA.

**Validation before analysis begins:** row counts per table reconciled against source, extraction date recorded, checksums on transferred files.

## Step 2: Automated data profiling (week 1–2)

Load the extract into a staging schema (see Pillar 2 — the same staging layer serves both) and run a standard profiling suite. Profile every candidate table for:

- **Volume & shape** — row counts, growth over time (via created/modified dates), column counts.
- **Completeness** — null/blank rates per column; columns that exist but are never used.
- **Cardinality & domains** — distinct values per column; full value distributions for low-cardinality columns (these are your candidate code tables/pick lists).
- **Referential integrity** — orphaned foreign keys, duplicate natural keys, dangling relationships.
- **Patterns & formats** — date ranges (find the 1900-01-01 sentinels), embedded delimiters, free-text fields that actually hold structured data, inconsistent casing/formats in identifiers.
- **Temporal activity** — transaction volumes by month/year to reveal seasonality, active vs. dormant records, and realistic data retention needs.

Tooling: keep this as a versioned, reusable suite (e.g., SQL scripts + a Python profiling layer such as `great_expectations`/`ydata-profiling`, or your ETL tool's profiler) so every project starts from the same baseline instead of ad-hoc queries.

## Step 3: Current-state process inference (week 2–3)

This is the step that feeds **Assess & Define** directly. Legacy data encodes how the client actually operates:

- **Configuration mining** — extract legacy code tables, statuses, types, categories, org/location hierarchies, roles, and workflow states. Map each to the equivalent configuration area in your product. Flag values with zero usage (don't configure what they never used) and high-usage values with no obvious product equivalent (gap or customization candidates).
- **Process mining (lightweight)** — from timestamped transactional data, reconstruct actual process flows: sequence of status changes, cycle times between steps, rework loops, approval chains. Compare against what the client *says* their process is in workshops — the deltas are your best discovery questions.
- **Exception analysis** — records that violate the client's stated rules (e.g., orders shipped before approval) reveal undocumented workarounds that must be either supported or explicitly retired.
- **Volume-based scoping** — which modules/entities carry real volume, informing phasing and effort estimates.

## Step 4: Deliverables into Assess & Define

1. **Current State Data Profile** — per-entity profile with volumes, quality metrics, and value distributions. Appendix to current-state documentation.
2. **Configuration Recommendations from Data** — a table mapping each discovered legacy configuration element → recommended product configuration → open questions. This becomes pre-read for configuration workshops, converting them from blank-page discovery into validation sessions.
3. **Data Quality Issue Log** — every defect found, with severity, affected volume, and a proposed disposition (fix at source / transform in ETL / accept). Client owns remediation decisions; opening this log in week 2 gives them months of runway instead of weeks.
4. **Conversion Scope & Risk Register** — entities in/out of scope, historical depth to convert, known risks (e.g., free-text fields requiring parsing, merged entities requiring survivorship rules).

## Anti-patterns to avoid

- Waiting for "clean" data before profiling — profiling *finds* the dirt; that's the point.
- Profiling only in-scope tables — cheap to profile everything; scope decisions should follow the data.
- Presenting raw profiling output to clients — always translate to business language ("14% of customer records lack a valid state code, which blocks tax configuration") with a recommended action.
