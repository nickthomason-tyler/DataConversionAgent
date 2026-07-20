# DataConversionAgent

Shift-left data conversion for EPL (Energov / Permitting & Licensing)
implementations: process playbook, launch plan, and the conversion guidance
agent. The goal is to begin conversion activities at project commencement —
profiling the client's legacy data to power Assess & Define, running
iterative ETL mock cycles into the Data Conversion Template (DCT) in parallel
with configuration, and giving teams an AI agent for best practices,
technical guidance, and product expertise.

## Contents

| Path | What it is |
|---|---|
| [`docs/data-conversion-process/`](./docs/data-conversion-process/README.md) | The three-pillar process playbook (early data analysis, initial ETL migration, guidance agent) plus the [technical launch playbook](./docs/data-conversion-process/04-launch-playbook.md) (~10–12 weeks to a live pilot) |
| [`agent/`](./agent/README.md) | Phase-1 guidance agent: runnable Python service on the Anthropic SDK tool runner, with knowledge-base retrieval, DCT dictionary lookup, mapping-workbook and profiling tools, per-client project context, and an eval harness |

## Quick start (agent)

```bash
cd agent
pip install -e .
export ANTHROPIC_API_KEY=...   # or `ant auth login`
python -m conversion_agent.cli example-client
```

## Where to start

1. Read the [process overview](./docs/data-conversion-process/README.md).
2. Follow the [launch playbook](./docs/data-conversion-process/04-launch-playbook.md) — the first-week checklist is at the bottom.
3. `agent/dct/dictionary.yaml` is generated from the real DCT-DB release (V2025.2.01: 309 tables, 2,108 columns). On each new DCT release, regenerate it with `agent/dct/build_dictionary.py` from the release's datatype spreadsheet and Word documentation.
