# Launch Playbook — Technical Steps to Get Off the Ground

A step-by-step build sequence from zero to a piloted, reusable conversion capability. Steps are ordered by dependency; durations assume 1–2 dedicated engineers plus a part-time conversion SME. Total: roughly 10–12 weeks to a live pilot, with the agent's first phase landing around week 8.

```
Stage 0        Stage 1         Stage 2          Stage 3         Stage 4        Stage 5
Foundations ─► Extraction  ─►  Profiling &  ─►  Template DB &   Pilot       ─► Agent
(wk 1-2)       packages        staging          ETL core        project        Phase 1
               (wk 2-4)        (wk 3-5)         (wk 4-7)        (wk 6-10)      (wk 8-12)
```

---

## Stage 0 — Foundations (weeks 1–2)

### 0.1 Create the tooling repository

One repo (`data-conversion-toolkit`) holds all reusable assets; each client project gets its own repo created from a template. Structure:

```
data-conversion-toolkit/
├── extraction/
│   ├── mssql/            # SQL Server extraction package
│   └── oracle/           # Oracle extraction package
├── profiling/            # profiling suite (SQL + Python)
├── pipeline/
│   ├── staging/          # staging DDL + loaders
│   ├── conformed/        # dbt models: cleaning/standardization
│   └── template/         # dbt models: conversion template DB mappings
├── dq/                   # data quality rule library (Great Expectations suites)
├── reconciliation/       # report generator
├── workbook/             # mapping workbook schema + validation script
├── agent/                # Pillar-3 agent (added Stage 5)
├── docs/                 # this playbook + runbooks
└── project-template/     # cookiecutter for per-client project repos
```

- [ ] Create repo with branch protection, CODEOWNERS, and CI (lint + unit tests on PR).
- [ ] Add `project-template/` as a cookiecutter/copier template: parameterized by client name, source system type, in-scope entities.

### 0.2 Provision the conversion environment

Per-client isolated environments, cheap to create and destroy:

- [ ] **Database**: PostgreSQL (or SQL Server if your template DB requires it) — one instance per client project, three schemas: `staging`, `conformed`, `template`. Provision via IaC (Terraform module) so `terraform apply -var client=acme` stands up a full environment.
- [ ] **Compute**: a small runner (container or VM) for pipeline execution; CI runner can double for this at pilot scale.
- [ ] **Secure file transfer**: SFTP endpoint or cloud bucket with per-client prefixes, SSE encryption, and expiring upload credentials for clients.
- [ ] **Secrets**: vault/parameter store for per-client DB credentials; nothing in repos.
- [ ] **Access control**: per-client DB roles; analysts get read on all three schemas, write only via pipeline runs.

### 0.3 Security & compliance baseline (parallel track)

- [ ] Data Processing Agreement template + security one-pager for client security teams (encryption, retention, deletion-on-project-close, subprocessors).
- [ ] Data classification rule: which fields are PII and the masking policy for non-production use.
- [ ] Retention automation: environment teardown checklist + scheduled reminder at project close.

**Exit criteria:** `terraform apply` produces a working per-client environment; empty toolkit repo with CI green; DPA template approved.

---

## Stage 1 — Extraction packages (weeks 2–4)

Two dialect variants, identical output contract.

### 1.1 Define the output contract first

- [ ] Extracts land as **UTF-8 CSV (or Parquet) + a manifest JSON** per run: table name, row count, extraction timestamp, source query hash, file checksums. The manifest is what reconciliation validates against.
- [ ] Normalization at extract time: ISO-8601 dates, explicit NULL token, documented decimal precision, Oracle empty-string-vs-NULL rule decided and written down.

### 1.2 Build the packages

- [ ] **SQL Server**: PowerShell + `bcp`/`Invoke-SqlCmd` script set; parameterized by table list; batched via `OFFSET/FETCH` for large tables.
- [ ] **Oracle**: shell + `sqlplus`/`expdp`-to-flat-file scripts, same parameters, same manifest output.
- [ ] Both also capture **schema DDL** (tables, PK/FK constraints, indexes, row counts) into a `schema.json` — profiling and the agent both consume this.
- [ ] Package as a zip a client DBA can run with one documented command and no internet access; include a README written for the *client's* DBA, not your team.

### 1.3 Validate

- [ ] Test against seeded local instances of SQL Server and Oracle (Docker: `mcr.microsoft.com/mssql/server`, `gvenzl/oracle-free`) in CI, including a table with every awkward type you support (CLOB, nested delimiters, sentinel dates, unicode).
- [ ] Loader in `pipeline/staging/` ingests the extract into `staging.*` tables verbatim + `load_id`, `extracted_at` columns, and fails loudly on checksum/row-count mismatch vs. manifest.

**Exit criteria:** round-trip test green in CI for both dialects: seeded source → extract → staging load → row counts and checksums match.

---

## Stage 2 — Profiling suite (weeks 3–5, overlaps Stage 1)

### 2.1 Automated profiling layer

- [ ] Python package in `profiling/` (ydata-profiling or hand-rolled SQL generators) that runs against `staging` and emits per-table metrics to a `profiling_results` table: row counts, null rates, distinct counts, min/max, value distributions for low-cardinality columns, date ranges, format-pattern detection.
- [ ] Referential-integrity checker: uses `schema.json` FKs where declared, plus name-convention inference (`*_id` columns) where not; outputs orphan counts.
- [ ] Temporal activity report: monthly record volumes per entity from created/modified timestamps.

### 2.2 Report generation

- [ ] A renderer that turns `profiling_results` into the **Current State Data Profile** (HTML/Markdown), with a business-language summary section written per entity.
- [ ] A **configuration-mining extractor**: dumps candidate code tables (low-cardinality columns + dedicated lookup tables) with usage counts into a review spreadsheet — the raw input for "Configuration Recommendations from Data."

**Exit criteria:** one command (`make profile CLIENT=acme`) produces the full profile report and config-mining workbook from a loaded staging schema.

---

## Stage 3 — Template DB, mapping workbook, ETL core (weeks 4–7)

### 3.1 Codify the conversion template database

- [ ] Commit the template DB schema as versioned DDL in `pipeline/template/` — if it currently lives as an Excel template or an undocumented DB, this step is extracting it into code.
- [ ] Write the **data dictionary** as structured YAML/JSON alongside the DDL: per column — description, valid values, which product configuration it depends on, required/optional. This single artifact later powers workbook validation *and* the agent.

### 3.2 Mapping workbook as a governed artifact

- [ ] Define the workbook schema (source, target, rule, crosswalk ref, default, status ∈ {draft, confirmed, blocked-on-config}, owner, date). Keep the working format a spreadsheet (analyst-friendly) but store canonically as CSV in the project repo so it diffs in PRs.
- [ ] Validation script in CI: every target column exists in the dictionary, every crosswalk value is legal, no confirmed mapping without an owner. A mapping change is a pull request.
- [ ] Code generator: emits dbt model stubs / crosswalk seed tables from the workbook, so the workbook literally drives the pipeline rather than describing it.

### 3.3 Transformation pipeline (dbt)

- [ ] dbt project over the three schemas: `staging` (sources) → `conformed` models (typing, dedupe, standardization) → `template` models (workbook-generated mappings + crosswalk joins).
- [ ] Great Expectations (or dbt tests) suites in `dq/`: a shared rule library (valid date, code-in-crosswalk, required-field, referential) instantiated per project. **Violations are logged to a `dq_issue` table with source row references — never silently dropped.**
- [ ] Run manifest: every pipeline run writes `load_id`, workbook git SHA, row counts per layer per entity.

### 3.4 Reconciliation report generator

- [ ] Script that joins run manifests + dq results into the per-cycle **Reconciliation Report**: layer-by-layer row counts with categorized drops, control totals, DQ trend vs. previous cycle, and a random field-audit sample sheet.

**Exit criteria:** end-to-end demo on synthetic data — extract → staging → profile → draft workbook → generated dbt models → template DB load → reconciliation report — from a single documented command sequence.

---

## Stage 4 — Pilot project (weeks 6–10, overlaps Stage 3)

Pick the pilot deliberately: a friendly client, one source system, modest volume, and an implementation lead who buys into the process.

- [ ] Week 1: run the kickoff data-access checklist for real; ship the extraction package; stand up the client environment via Terraform.
- [ ] Week 2–3: staging load + profiling; deliver the Current State Data Profile and config-mining workbook to the Assess & Define team; open the DQ Issue Log.
- [ ] Week 4–6: Mock 1 with provisional defaults; first reconciliation report; review with Client Data Steward.
- [ ] Throughout: **log every manual workaround** — each one is a backlog item for the toolkit. The pilot's job is to find where the tooling is thin.
- [ ] Retro at Mock 1: measure time-to-first-profile, time-to-Mock-1, % mappings auto-generated from workbook, defect count categories. These are your baseline metrics for the business case.

**Exit criteria:** Mock 1 delivered on a real client; toolkit backlog triaged; go/no-go on rolling the process to the next two projects.

---

## Stage 5 — Agent Phase 1 (weeks 8–12, overlaps pilot)

Only the internal Q&A phase at launch (see [03-conversion-agent.md](./03-conversion-agent.md) for the full roadmap).

- [ ] **Curate the knowledge base**: this playbook, the template DB data dictionary (3.1 — already structured), product configuration guides, and the pilot's sanitized decisions. Markdown in the toolkit repo; the repo *is* the corpus.
- [ ] **Build**: Claude Agent SDK service with two MCP servers to start — (1) knowledge retrieval over the corpus, (2) read-only template-dictionary lookup. System prompt enforces grounding + citation and "escalate, don't guess."
- [ ] **Surface**: Slack/Teams bot for the implementation team. No client access in Phase 1.
- [ ] **Evaluate**: 30–50 question golden set drawn from real consultant questions during the pilot; score weekly; ship to the wider team when accuracy is consistently acceptable to the conversion SME.
- [ ] Phase 2 (mapping copilot) begins only after the pilot's mapping workbook exists, giving you real data to test suggestion quality against.

**Exit criteria:** agent answering the golden set acceptably, in the team's chat tool, with citations; Phase 2 scoped from pilot experience.

---

## Launch sequencing summary

| Week | Engineering track | Process/pilot track |
|---|---|---|
| 1–2 | Repo, IaC environments, security baseline | Pilot client selected; DPA in legal review |
| 2–4 | Extraction packages + staging loader | Kickoff checklist finalized |
| 3–5 | Profiling suite + report renderer | — |
| 4–7 | Template DDL, dictionary, workbook tooling, dbt core, DQ library, recon generator | Pilot kickoff (wk 6); extract delivered |
| 6–10 | Toolkit fixes from pilot friction | Pilot profiling → Mock 1 → retro |
| 8–12 | Agent Phase 1 build + eval | Golden question set collected from pilot |

## First-week checklist (literally where to start Monday)

1. Create `data-conversion-toolkit` repo with the directory skeleton and CI.
2. Write the Terraform module for the per-client Postgres environment; apply it once for a `dev` client.
3. Stand up Docker SQL Server + Oracle with seeded awkward-type test data.
4. Draft the extraction output contract (manifest schema) and get the conversion SME to sign off.
5. Send the DPA/security one-pager to legal.
6. Shortlist pilot clients with the delivery leads.
