# Pillar 3 — Conversion Guidance Agent

Goal: an AI agent that gives implementation teams and clients on-demand best practices, technical guidance, and domain/product expertise throughout the conversion — turning your best consultant's knowledge into something every project can access.

## What the agent should do

**For your implementation teams**

- Answer product and template-DB questions: "What does the template expect in `CUST_TYPE`? What are valid values and what configuration do they depend on?"
- Suggest mappings: given a profiled legacy column (name, type, sample values, distributions from Pillar 1), propose target fields and crosswalks, with confidence and rationale.
- Generate and review transformation SQL against your pipeline conventions.
- Explain DQ failures and propose dispositions consistent with past decisions on similar issues.
- Retrieve precedent: "How did we handle mid-year balance conversion for clients on legacy system X?"

**For clients (tighter guardrails)**

- Explain the conversion process, current mock-cycle status, and what's needed from them next.
- Help data stewards interpret the DQ Issue Log and choose dispositions.
- Answer product domain questions during Assess & Define ("How does the new system handle multi-site inventory?").

## Architecture

```
Knowledge layer (RAG)                    Tool layer (MCP)
├─ Product docs & config guides         ├─ Template DB schema/dictionary (read)
├─ Template DB data dictionary          ├─ Profiling results store (read)
├─ Conversion runbooks & playbooks      ├─ Mapping workbook (read; write = draft-only)
│  (Pillars 1 & 2 of this repo)         ├─ DQ issue log (read/comment)
├─ Past project artifacts (sanitized:   └─ SQL sandbox against staging (read-only,
│  mappings, DQ decisions, lessons)          row-limited, masked)
└─ Domain/industry best practices
                └──────────┬──────────┘
                     Agent (Claude via Agent SDK)
                    /                \
        Internal surface          Client surface
        (full tools, Slack/       (knowledge + status only,
         Teams + CLI)              no direct DB access)
```

Build notes:

- **Claude Agent SDK** for the agent loop; **MCP servers** for each tool integration so the same tools serve both chat and pipeline automation.
- **Retrieval over fine-tuning.** Your knowledge changes every release and every project; RAG over versioned docs stays current, is auditable, and lets you trace every answer to a source.
- **Project context injection**: the agent is instantiated per client project with that project's mapping workbook, profile results, and DQ log so answers are situated, not generic.
- Structure the knowledge base as versioned markdown in a repo (like this one) — that makes the docs, the agent's knowledge, and your methodology the same artifact.

## Guardrails

- **Human-in-the-loop for anything that changes state.** The agent drafts mappings and SQL; a consultant confirms. Confirmed decisions get written back to the knowledge base, so the agent improves with every project.
- **Data minimization**: the agent sees schemas, profiles, and aggregates by default — not raw client records. Row-level access only via the masked, read-only sandbox, and never on the client surface.
- **Grounding and citation required**: answers must cite the doc/decision they came from; the agent must say "I don't know — flagging for the Conversion Lead" rather than guess on product behavior.
- **Client-surface scope lock**: no cross-client information, no raw data access, no commitments on timeline/scope (route those to the project team).

## Phased rollout

| Phase | Scope | Success measure |
|---|---|---|
| 1. Internal Q&A | RAG over product docs, template dictionary, and this playbook; team chat access | Consultants prefer it to searching docs; answer accuracy spot-checked weekly |
| 2. Mapping copilot | Profiling-results + mapping-workbook tools; draft mapping suggestions | % of drafted mappings accepted without edit; time-to-first-draft mapping workbook |
| 3. Pipeline integration | Auto-draft DQ dispositions and reconciliation narratives each mock cycle | Cycle-over-cycle reduction in manual analysis hours |
| 4. Client surface | Status + process Q&A for client data stewards | Client questions answered without consultant involvement; CSAT |

Start with Phase 1 — it needs no client data, carries the least risk, and immediately tests whether your knowledge base is good enough. Most of the work of building a useful agent is curating that knowledge base, and Pillars 1 and 2 of this playbook are its first two documents.
