# Shift-Left Data Conversion Process

A playbook for starting data conversion activities at **project commencement** instead of waiting for system configuration to complete. The process has three pillars, each with its own detailed guide:

| Pillar | Guide | Purpose |
|---|---|---|
| 1. Early Legacy Data Analysis | [01-early-data-analysis.md](./01-early-data-analysis.md) | Profile the client's legacy data in week 1 to power Assess & Define current-state documentation and drive configuration decisions |
| 2. Initial ETL Migration | [02-initial-etl-migration.md](./02-initial-etl-migration.md) | Repeatable pipeline from legacy SQL Server / Oracle into the data conversion template database, run in iterative mock cycles |
| 3. Conversion Guidance Agent | [03-conversion-agent.md](./03-conversion-agent.md) | An AI agent providing best practices, technical guidance, and domain/product expertise to teams and clients |
| Launch Playbook | [04-launch-playbook.md](./04-launch-playbook.md) | Step-by-step technical build sequence to get the initiative off the ground (~10–12 weeks to a live pilot) |

## Why shift left?

In the traditional model, conversion starts after configuration is signed off. That serializes the two longest workstreams in the project and means data surprises (quality problems, undocumented customizations, volumes) are discovered late, when they are most expensive.

In the shift-left model:

- **Data access is a kickoff deliverable**, not a mid-project task.
- **Data profiling informs configuration** rather than configuration dictating data mapping. The legacy data is the most truthful record of how the client actually operates — often more accurate than what workshops surface.
- **Conversion runs as iterative mock cycles** in parallel with configuration. Each cycle absorbs the configuration decisions made since the last one, so the final cutover conversion is a rehearsed, low-risk event.

## Timeline at a glance

```
Project phase:   Kickoff ──► Assess & Define ──► Configure ──► Test ──► Deploy
                    │               │                 │           │        │
Conversion:      Data access    Profiling &       Mock 1..N   Mock N+1  Cutover
                 & extraction   current-state     (iterate     (dress    (rehearsed)
                                analysis          mappings)    rehearsal)
```

## Operating model

**Roles**

- **Conversion Lead** — owns the pipeline, mock cycle schedule, and reconciliation sign-off.
- **Data Analyst** — runs profiling, produces the Current State Data Profile, maintains the mapping workbook.
- **Implementation Consultant** — owns Assess & Define outputs; consumes profiling findings; feeds configuration decisions back into mappings.
- **Client Data Steward** — provides access, answers data questions, signs off on data quality decisions and reconciliation results.

**Key artifacts (all versioned per client project)**

1. Data Access & Extraction Checklist (kickoff)
2. Current State Data Profile report (end of week 2–3)
3. Configuration Recommendations from Data (feeds Assess & Define)
4. Source-to-Target Mapping Workbook (living document)
5. Data Quality Issue Log (living document, client-owned remediation)
6. Mock Conversion Reconciliation Reports (one per cycle)
7. Cutover Runbook (final)

## Entry and exit criteria per phase

| Phase | Entry criteria | Exit criteria |
|---|---|---|
| Data Access | Signed DPA/security review; kickoff complete | Read-only extract or replica delivered; extraction validated against source row counts |
| Profiling & Analysis | Extract loaded to staging | Current State Data Profile + Configuration Recommendations delivered; DQ issue log opened |
| Mock cycles | Template DB schema confirmed; initial mappings drafted | Reconciliation within agreed tolerance; open DQ issues triaged; client sign-off per cycle |
| Cutover | Dress-rehearsal mock within tolerance; runbook walkthrough done | Production load reconciled and signed off |
