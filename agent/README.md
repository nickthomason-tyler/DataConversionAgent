# EPL Conversion Guidance Agent

The conversion agent is a project-isolated, internal Q&A and mapping copilot
for EPL (EnerGov / Permitting & Licensing) conversions. It packages governed
shared DCT and conversion knowledge while keeping real client artifacts outside
Git, in an approved projects root.

## Install and run

For development, install the package and its local quality tools:

```bash
cd agent
pip install -e ".[dev]"
export CONVERSION_AGENT_PROJECTS_ROOT=/approved/path/to/projects
conversion-agent example-client
```

The checked-in `clients/example-client` project remains a development fallback,
so the legacy module command continues to work from this checkout:

```bash
python -m conversion_agent.cli example-client
```

Use an explicit root to override the environment for one command:

```bash
conversion-agent example-client --projects-root /approved/path/to/projects
conversion-map input.xlsx output.xlsx --project example-client --llm
```

`--projects-root` takes precedence over `CONVERSION_AGENT_PROJECTS_ROOT`, which
takes precedence over the source-checkout example project. An installed wheel
has no fallback client storage: configure an approved external root before
loading a project.

The mapping and proposal interfaces retain their module forms and positional
arguments:

```bash
python -m conversion_agent.mapping.cli input.xlsx output.xlsx --rules rules.yaml
python -m conversion_agent.mapping.apply input.xlsx proposals.json output.xlsx
```

The equivalent console scripts are `conversion-map` and `conversion-apply`.
`conversion-map` also accepts additive `--project`, `--projects-root`,
`--backend`, `--model`, and `--debug` flags; it only calls a model with `--llm`.

## Project layout

Keep each real project as a direct child of the approved projects root. Do not
commit client workbooks, profiles, or overlay knowledge to this repository.

```text
/approved/path/to/projects/
└── example-client/
    ├── project.yaml                 # required
    ├── mapping_workbook.csv         # optional until mapping work begins
    ├── profile_summary.json          # optional until profiling completes
    └── knowledge/                    # optional Markdown-only project overlay
        └── local-rule.md
```

`project.yaml` uses schema version 1. `client_name`, `source_system`, `phase`,
and a unique non-empty `in_scope_entities` list are required. The lead and data
steward fields are optional. Older metadata that omits `schema_version` remains
compatible and is read as version 1.

```yaml
schema_version: 1
client_name: City of Exampleton
source_system: SQL Server (legacy permitting system)
phase: Mock 1
in_scope_entities: [permits, contacts, business_licenses]
conversion_lead: TBD
client_data_steward: TBD
```

The optional `knowledge/` overlay is for project-specific Markdown guidance.
It is searched only in that project session. Governed shared content cites as
`[source: <path> § <heading>]`; an overlay result is deliberately distinct:
`[project source: <project-id>/<path> § <heading>]` (that is,
`[project source: ...]`). Treat the latter as local project guidance, not a
shared standard.

## Packaged shared resources

The wheel contains the canonical shared runtime corpus:

```text
src/conversion_agent/resources/data/
├── dct/dictionary.yaml
└── knowledge/
```

`ResourceCatalog` loads these resources from the installed package. To rebuild
the DCT dictionary from an approved DCT release, install the optional builder
dependency and run `dct/build_dictionary.py`; review the generated packaged
resource before committing it.

```bash
pip install -e ".[dct-build]"
python dct/build_dictionary.py DCT-DB_datatypes.xlsx DCT-DB.docx V2025.2.01
```

## Tests and evaluations

The default test suite never needs live credentials:

```bash
python -m pytest tests -m 'not live' -v
```

Live backend tests are opt-in and must run only in an explicitly configured
Anthropic or Bedrock environment. The tests are always collected, then skip
without the required credential configuration, so the default offline suite
never sends a network request.

```bash
python -m pytest -m live -v
ANTHROPIC_API_KEY=... python -m pytest tests/guidance/test_live_smoke.py -m live -v
CONVERSION_AGENT_LIVE_BEDROCK=1 CONVERSION_AGENT_BACKEND=bedrock AWS_REGION=us-east-1 python -m pytest tests/guidance/test_live_smoke.py -m live -v
```

The Bedrock smoke command also requires a standard AWS credential source such
as `AWS_PROFILE` or `AWS_ACCESS_KEY_ID`; use the explicit
`CONVERSION_AGENT_LIVE_BEDROCK=1` opt-in when an instance role supplies those
credentials. To list these tests without contacting either backend, run
`python -m pytest --collect-only -m live`.

The golden-question runner uses the same settings, repository, resource catalog,
and guidance service as the CLI. It calls the live configured backend and writes
`evals/results.md` for SME review, so do not use it as an offline gate:

```bash
python evals/run_evals.py example-client --projects-root /approved/path/to/projects
```

For Bedrock, set `CONVERSION_AGENT_BACKEND=bedrock`, `AWS_REGION`, and standard
AWS credentials; the Anthropic backend uses its normal configured credentials.
Both backends are injected through the same service boundary.
