# Pillar 2 — Initial ETL Migration to the Conversion Template Database

Goal: a repeatable, versioned pipeline that moves data from the client's legacy database (SQL Server or Oracle) into your data conversion template database, run as **iterative mock cycles** starting at project commencement — not as a one-shot event after configuration freeze.

## Architecture: four layers

```
LEGACY (SQL Server / Oracle)
   │  extract (full or incremental, read-only)
   ▼
RAW / STAGING          ── exact mirror of source tables + load metadata
   │                      (load_id, extracted_at, source_system)
   ▼
CONFORMED              ── cleaned, typed, deduplicated, standardized;
   │                      DQ rules applied and violations logged, not dropped
   ▼
CONVERSION TEMPLATE DB ── your product's template schema; mapping rules
                          applied; ready for product import/validation
```

Principles:

- **Staging is untransformed.** Every downstream problem must be traceable back to the exact source rows. Never "fix" data in staging.
- **Transformations are code, not hand edits.** SQL/dbt/ETL-tool jobs in version control, per client project, branched from a shared template repo. A hand-edited spreadsheet cannot be re-run; a pipeline can be re-run every mock cycle at near-zero cost.
- **Every run is identified.** `load_id` on every row; a run manifest recording source extract date, mapping workbook version, and row counts in/out per layer.

## The mapping workbook

The single source of truth connecting legacy fields → template DB fields:

| Column | Content |
|---|---|
| Source table/column | Legacy location |
| Target table/column | Template DB location |
| Transformation rule | Plain-English + reference to the code that implements it |
| Value crosswalks | Legacy code → product configuration value (this is where configuration decisions land) |
| Default/derivation | What to do when source is null/invalid |
| Status | Draft / Confirmed / Blocked-on-config |
| Owner & decision date | Accountability |

At project start, many crosswalk targets are unknown because configuration isn't decided. That's expected: mark them `Blocked-on-config` and load with **provisional defaults**. Each configuration decision flips rows from provisional to confirmed — the workbook doubles as a progress metric for configuration itself.

## Mock cycle cadence

| Cycle | Timing | Purpose |
|---|---|---|
| **Mock 0** | Weeks 1–3 | Staging load only + profiling (Pillar 1). Proves access, volume handling, and extraction repeatability. |
| **Mock 1** | ~Week 4–6 | First end-to-end load into the template DB using draft mappings and provisional defaults. Expect high defect counts — the goal is a working pipeline and a real DQ baseline, not correctness. |
| **Mock 2..N** | Every 3–4 weeks | Re-extract, re-run with updated mappings reflecting configuration decisions and DQ remediation. Reconciliation gap must shrink every cycle. |
| **Dress rehearsal** | Pre-cutover | Full run under cutover timing conditions, executed from the runbook, timed, with client sign-off on reconciliation. |
| **Cutover** | Go-live | Identical to dress rehearsal with the final extract. Boring by design. |

## Reconciliation & validation framework

Every cycle produces a reconciliation report — this is the artifact the client signs:

1. **Row counts** per entity: source → staging → conformed → template (with documented, categorized drops: out-of-scope filter vs. DQ rejection vs. dedupe merge).
2. **Financial/control totals** where applicable (sum of balances, order totals) matched to the penny between source and target.
3. **DQ rule results** — pass/fail counts per rule, trended across cycles.
4. **Sample-based field audit** — random sample of records traced field-by-field from legacy to template, reviewed with the Client Data Steward.

## SQL Server / Oracle specifics

- Maintain **two dialect variants of the extraction package only**; from staging onward the pipeline is source-agnostic. Normalize at extract: dates to ISO-8601, encodings to UTF-8, `NUMBER`/`DECIMAL` precision mapped explicitly, Oracle empty-string-as-NULL handled deliberately.
- Prefer extraction via bulk export (BCP / `expdp` / `SELECT ... OFFSET-FETCH` batching) over row-by-row reads for volume.
- Capture the source schema (DDL, constraints, indexes) alongside the data — constraints document intended integrity even where the data violates it.

## Build-once assets (the payoff)

The first project pays to build; every subsequent project reuses:

1. Extraction packages (SQL Server + Oracle)
2. Staging + conformed schema templates and load framework
3. Profiling suite (Pillar 1)
4. Mapping workbook template with your product's template DB pre-populated on the target side
5. DQ rule library and reconciliation report generator
6. Cutover runbook template
