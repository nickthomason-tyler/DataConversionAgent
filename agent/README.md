# EPL Conversion Guidance Agent

Phase-1 scaffold for the conversion guidance agent (Pillar 3 of the
[data conversion process](../docs/data-conversion-process/README.md)): an
internal Q&A and mapping copilot for teams migrating client legacy data into
the Data Conversion Template (DCT) and on to configured EPL databases.

## Architecture decision

Three ways to build this were considered:

| Option | Why / why not |
|---|---|
| **Anthropic SDK Tool Runner** (chosen) | The agent loop runs inside a service *we* host. Client data never leaves our infrastructure except as prompts to the API; tools are plain Python functions in this codebase; per-client context is injected at construction time. Best fit for an enterprise service embedded in the conversion toolkit. |
| Claude Agent SDK (Claude Code as a library) | Ships a filesystem/bash agent harness. More power than Phase 1 needs, and its built-in tools (bash, file write) are the wrong default posture around client data. Revisit for Phase 3 pipeline automation. |
| Managed Agents (Anthropic-hosted sessions) | Anthropic hosts the loop and a sandbox. Attractive for ops-free scaling, but Phase 1 keeps data custody simplest by self-hosting. Revisit if we want hosted scheduled runs. |

## Layout

```
agent/
├── pyproject.toml
├── src/conversion_agent/
│   ├── config.py        # per-client project context loading
│   ├── knowledge.py     # keyword retrieval over the markdown knowledge base
│   ├── tools.py         # the agent's tools (@beta_tool functions)
│   ├── agent.py         # system prompt + tool-runner loop
│   └── cli.py           # interactive chat: python -m conversion_agent.cli <client>
├── knowledge/           # the RAG corpus — versioned markdown (playbook, guides)
├── dct/dictionary.yaml  # DCT data dictionary (structured; also powers workbook validation)
├── clients/example-client/  # sample per-client project context
│   ├── project.yaml
│   ├── mapping_workbook.csv
│   └── profile_summary.json
└── evals/
    ├── golden_questions.yaml
    └── run_evals.py
```

## Running

```bash
cd agent
pip install -e .
export ANTHROPIC_API_KEY=...   # or `ant auth login`
python -m conversion_agent.cli example-client
```

## Running on Amazon Bedrock (corporate account)

The backend switch is built in (`src/conversion_agent/backend.py`). On a
machine using Claude through Bedrock:

```bash
git clone https://github.com/nickathomason/DataConversionAgent.git
cd DataConversionAgent/agent
pip install -e . "anthropic[bedrock]" lxml

export CONVERSION_AGENT_BACKEND=bedrock
export AWS_REGION=us-east-1            # your Bedrock region
# plus standard AWS credentials: AWS_PROFILE, or AWS_ACCESS_KEY_ID /
# AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN, or an instance role

python -m conversion_agent.cli example-client
```

With `CONVERSION_AGENT_BACKEND=bedrock`, the guidance agent and the Lane 2
mapper use the `AnthropicBedrockMantle` client and Bedrock model IDs
(`anthropic.claude-opus-4-8`) automatically — no code changes. The mapping
engine's deterministic lanes (`conversion_agent.mapping.cli`, `apply`) make
no model calls at all and run identically anywhere.

Notes for the Bedrock environment:
- Verify the account has the target Claude model enabled in the chosen region.
- Structured outputs and tool use (everything Lane 2 uses) are supported on
  Bedrock; the tool-runner loop in `agent.py` should be smoke-tested once
  against the installed SDK version.
- Client workbooks and per-client pipeline scripts are intentionally NOT in
  this repository — transfer them separately through an approved channel.

## How it works

1. `config.py` loads the client's project file, mapping workbook, and profiling
   summary, and `agent.py` builds a system prompt with that context injected.
   The stable prompt sections carry a `cache_control` breakpoint so repeated
   turns hit the prompt cache; volatile per-project context comes after it.
2. Tools are defined with the SDK's `@beta_tool` decorator and executed by
   `client.beta.messages.tool_runner(...)` — the SDK drives the
   request → tool → result loop; we only implement the functions.
3. Grounding rules in the system prompt require citations to knowledge-base
   files or dictionary entries, and force "I don't know — escalating to the
   Conversion Lead" over guessing.

## Phase roadmap (from the process docs)

1. **Internal Q&A** (this scaffold) — knowledge retrieval + DCT dictionary.
2. **Mapping copilot** — add profiling-driven mapping suggestions with
   draft-only writes to the workbook (human confirms via PR).
3. **Pipeline integration** — auto-draft DQ dispositions and reconciliation
   narratives each mock cycle.
4. **Client surface** — separate deployment with scope-locked tools
   (status + process Q&A only, no raw data access).

## Evals

`evals/golden_questions.yaml` holds the golden set (grow it from real
consultant questions during the pilot). `python evals/run_evals.py` runs each
question through the agent and writes answers for SME review — grade weekly,
ship Phase 1 to the wider team when accuracy is consistently acceptable.

## Enterprise hardening backlog (before wide rollout)

- Serve over HTTP (FastAPI) behind SSO; one worker pool, per-client context per request.
- Conversation persistence + audit log of every tool call and answer.
- Swap keyword retrieval for embeddings once the corpus outgrows it (keep the
  same `search_knowledge_base` tool contract).
- Read-only, row-limited, masked SQL sandbox tool against `staging` (Phase 2+).
- Rate limiting, cost telemetry (`usage` per turn), and prompt-cache hit monitoring.
