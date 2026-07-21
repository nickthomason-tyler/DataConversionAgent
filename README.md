# DataConversionAgent

Shift-left data conversion for EPL (EnerGov / Permitting & Licensing): a
conversion process playbook, launch plan, and project-isolated guidance and
mapping agent. The workflow starts conversion activities at project commencement
and supports iterative ETL mock cycles alongside configuration.

## Contents

| Path | What it is |
|---|---|
| [`docs/data-conversion-process/`](./docs/data-conversion-process/README.md) | The three-pillar conversion process and technical launch playbook. |
| [`agent/`](./agent/README.md) | Installable guidance and mapping package, project repository, CLIs, tests, and SME evaluation runner. |
| [`agent/src/conversion_agent/resources/data/`](./agent/src/conversion_agent/resources/data/) | Canonical packaged DCT dictionary and governed shared Markdown knowledge. |

## Quick start

The package can use an approved external project root. Real client artifacts
remain outside this repository and move only through approved channels.

```bash
cd agent
pip install -e ".[dev]"
export CONVERSION_AGENT_PROJECTS_ROOT=/approved/path/to/projects
conversion-agent example-client
```

The checked-in `clients/example-client` is a safe development fallback for a
source checkout. Existing module commands remain supported:

```bash
python -m conversion_agent.cli example-client
python -m conversion_agent.mapping.cli input.xlsx output.xlsx --rules rules.yaml
```

See the [agent guide](./agent/README.md) for project schema versioning, optional
`knowledge/` project overlays, configuration precedence, mapping flags,
offline-versus-live tests, and packaged-resource maintenance.

## Where to start

1. Read the [process overview](./docs/data-conversion-process/README.md).
2. Follow the [launch playbook](./docs/data-conversion-process/04-launch-playbook.md).
3. Use the [agent guide](./agent/README.md) to prepare an approved project root
   and run the guidance or mapping workflows.
