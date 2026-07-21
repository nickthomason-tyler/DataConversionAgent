# Scalable Shared-Core Refactor Design

**Date:** 2026-07-20

**Status:** Approved design

**Scope:** Guidance agent, mapping pipeline, shared core, packaging, CLIs, and automated tests

## 1. Context

The repository is a capable Phase 1 prototype with useful separations between
project context, shared conversion knowledge, deterministic mapping, model-assisted
mapping, proposal validation, and surgical workbook write-back. It works best as
an editable-source checkout serving one project at a time.

The current implementation is not safe to reuse concurrently across projects.
The guidance tools obtain their active project from a process-global variable, so
constructing a second agent changes the data visible to the first. Project and
shared-resource paths are tied to the source tree, and the built wheel excludes
the knowledge corpus, DCT dictionary, and example data that runtime code expects.
The package also omits dependencies used by supported mapping and dictionary
workflows. Project files have no schema validation, several operations can return
unbounded data, and there is no automated regression suite.

This refactor will turn the prototype into a project-isolated shared core while
preserving the existing command-line workflows. It will not add an HTTP service.

## 2. Goals

1. Allow multiple project contexts and guidance sessions to coexist safely in
   one Python process without sharing project data or conversation state.
2. Keep one installable `conversion_agent` package with focused internal modules
   for core configuration, projects, resources, guidance, mapping, and CLIs.
3. Load real projects from a configurable external filesystem root while retaining
   `agent/clients/example-client` as a safe development fallback.
4. Preserve the conventional project filenames: `project.yaml`,
   `mapping_workbook.csv`, and `profile_summary.json`.
5. Validate project metadata and artifacts with actionable file- and field-level
   errors. Legacy project metadata without a schema version remains compatible as
   schema version 1.
6. Search governed shared knowledge plus an optional per-project `knowledge/`
   overlay, with citations that make the source scope clear.
7. Harden both the guidance and mapping subsystems without changing their
   established domain behavior or existing module-based CLI commands.
8. Produce an ordinary wheel that contains its shared runtime resources and can
   run outside the repository checkout.
9. Add offline automated tests for isolation, validation, mapping behavior,
   workbook preservation, packaging, and compatibility.

## 3. Non-goals

- No FastAPI or other HTTP service.
- No SSO, authorization service, conversation persistence, rate limiting, or
  centralized audit-log implementation.
- No S3, database, or SharePoint project repository implementation.
- No embeddings or hosted vector database. Keyword retrieval remains the default.
- No automatic migration or commit of confidential client artifacts.
- No change to the DCT business schema or the core deterministic matching rules
  unless a characterization test exposes an existing defect.
- No live model credentials required for the default test suite or CI.

## 4. Architectural Approach

Use a modular monolith: one distribution and one top-level Python package, with
explicit contracts between focused modules. Storage and model integrations sit
behind narrow protocols, but the refactor will not introduce dynamic plugin
discovery.

The principal runtime flow is:

1. A CLI adapter resolves application settings.
2. A project repository validates a project identifier and loads one immutable
   `ProjectContext` snapshot from the configured projects root.
3. `GuidanceService` or `MappingService` receives that context explicitly.
4. Guidance tools are constructed for the specific session and close over that
   session's context. No active-project global exists.
5. Shared DCT and knowledge resources are process-safe and may be cached because
   they do not contain project state.
6. Results and failures return through typed application reports or typed errors;
   CLI adapters are responsible only for rendering them and selecting exit codes.

This boundary allows a future HTTP adapter to call the same services without
changing project isolation or domain logic.

## 5. Proposed Package Boundaries

```text
conversion_agent/
├── core/
│   ├── settings.py       # AppSettings and precedence rules
│   └── errors.py         # typed application errors and exit-code categories
├── projects/
│   ├── models.py         # validated immutable project models
│   ├── repository.py     # ProjectRepository protocol
│   └── filesystem.py     # safe external-filesystem implementation
├── resources/
│   ├── catalog.py        # packaged DCT and shared-knowledge access
│   ├── knowledge.py      # shared + project-overlay retrieval
│   └── data/
│       ├── dct/dictionary.yaml
│       └── knowledge/    # canonical governed shared corpus
├── guidance/
│   ├── service.py        # project lookup and session creation
│   ├── session.py        # prompt, model loop, bounded history
│   ├── tools.py          # project-bound tool factory
│   └── backends.py       # injectable Anthropic/Bedrock client factory
├── mapping/
│   ├── model.py
│   ├── workbook.py
│   ├── match.py
│   ├── llm.py
│   ├── validation.py
│   ├── writeback.py
│   └── service.py
└── cli/
    ├── common.py
    ├── guidance.py
    ├── mapping.py
    └── apply.py
```

The existing modules `conversion_agent.cli`, `conversion_agent.mapping.cli`, and
`conversion_agent.mapping.apply` remain as thin compatibility wrappers. Existing
positional arguments and defaults continue to work. The distribution also adds
the convenience entry points `conversion-agent`, `conversion-map`, and
`conversion-apply`; they delegate to the same adapters and do not replace the
module commands.

## 6. Configuration

`AppSettings` is an immutable validated object. Settings resolve in this order,
from highest to lowest precedence:

1. Explicit function or CLI argument.
2. Environment variable.
3. Development default.

The project root uses `--projects-root`, then
`CONVERSION_AGENT_PROJECTS_ROOT`, then the repository's existing
`agent/clients` directory when that development directory exists. An installed
distribution with no configured external root must fail with a message explaining
how to set the root; it must not silently create a storage location.

Backend selection continues to support the current environment variables and
defaults. Backend and model settings are represented in `AppSettings` and injected
into services rather than read repeatedly from global environment state. CLI flags
for backend or model selection are additive and may override environment values.

Guidance history is bounded by `CONVERSION_AGENT_MAX_HISTORY_MESSAGES`, with a
default of 40 messages. Tool output is bounded by a default maximum of 50,000
characters. Mapping-row retrieval defaults to 100 rows per call and permits at
most 500. These values are application settings, not project metadata.

## 7. Project Repository and Validation

`ProjectRepository` exposes a single required operation:

```python
load(project_id: str) -> ProjectContext
```

`FilesystemProjectRepository` applies these rules:

- A project identifier is a slug containing ASCII letters, digits, dots,
  underscores, or hyphens. It cannot be empty, start with a dot, equal `.` or
  `..`, contain a path separator, or be an absolute path.
- The resolved project directory must remain a direct child of the resolved
  projects root. Symlink resolution cannot escape that root.
- `project.yaml` is required.
- `mapping_workbook.csv` and `profile_summary.json` are optional because early
  projects may not have produced them yet. When absent, tools return an explicit
  not-yet-available result. When present, they must validate fully.
- An optional `knowledge/` directory may contain Markdown files. Other file types
  are ignored. Symlinks that resolve outside the project directory are rejected.
- Files are read as UTF-8 and parse errors identify the exact artifact.

Project metadata schema version 1 contains:

- `schema_version`: positive integer; omitted means version 1.
- `client_name`: required non-empty string.
- `source_system`: required non-empty string.
- `phase`: required non-empty string.
- `in_scope_entities`: required list of unique non-empty strings.
- `conversion_lead`: optional string.
- `client_data_steward`: optional string.
- Additional keys are preserved in a read-only metadata mapping for backward
  compatibility, while known fields remain typed.

Mapping CSV validation requires the current columns:
`source_table`, `source_column`, `target_table`, `target_column`, `rule`, `status`,
and `owner`. Empty files, duplicate headers, missing headers, and malformed rows
produce validation errors. Status strings remain open to project-specific values,
but are normalized for counting without modifying their displayed source value.

Profile JSON must be an object. If `entities` is present, it must be an object
whose values are objects. The validator preserves additional profile keys so the
schema can evolve without breaking older consumers.

The resulting `ProjectContext` and its nested public collections are immutable or
exposed through read-only interfaces. Repositories return a new snapshot on each
load; project data is not cached by default, preventing stale CLI reads.

## 8. Shared and Project Knowledge

The shared knowledge corpus and DCT dictionary become package resources loaded
with `importlib.resources`, not paths inferred from `__file__` outside the Python
package. Runtime knowledge and dictionary data have one canonical packaged source.
Repository documentation links to that source rather than maintaining an
unsynchronized second runtime copy.

`ResourceCatalog` lazily loads and caches the immutable DCT dictionary and parsed
shared knowledge index once per process. Tests verify that the cache contains no
project artifacts.

For a guidance session, `KnowledgeIndex` merges:

1. Governed shared knowledge.
2. Markdown sections from the current project's optional `knowledge/` directory.

Search results retain their scope. Shared citations continue to render as
`[source: <path> § <heading>]`; project-overlay citations render as
`[project source: <project-id>/<path> § <heading>]`. The tool never searches or
returns another project's overlay.

Keyword scoring remains the current default, but tokenization and section parsing
become independently testable. The retrieval interface remains replaceable by a
future embedding implementation.

## 9. Guidance Subsystem

`GuidanceService` depends on `AppSettings`, `ProjectRepository`,
`ResourceCatalog`, and a `ModelBackendFactory`. Its public operation is:

```python
open_session(project_id: str) -> GuidanceSession
```

`GuidanceSession` owns its immutable `ProjectContext`, project-bound tools,
system prompt, backend client, and conversation history. Tool functions are
created by a factory or bound object and capture the session context directly.
The process-global `set_project()` mechanism is removed.

System-prompt caching retains a stable shared prefix followed by volatile project
context. The source system in mapping or guidance prompts comes from project
context when present; model prompts must not assume New World Permitting. When no
project is supplied to the standalone mapping CLI, model prompts use source-neutral
legacy-system language.

History truncation removes the oldest complete user/assistant pair when the
configured message limit is exceeded. The most recent pair is never split.
Backend failures do not append a fabricated assistant response. Tool results are
bounded before entering the model context and indicate when rows or characters
were truncated.

Backends implement a narrow factory contract. Anthropic and Bedrock remain the
supported production implementations. Tests use a deterministic fake backend and
never require credentials.

## 10. Mapping Subsystem

`MappingService` coordinates parsing, deterministic matching, optional model
matching, proposal validation, write-back, and verification. Its core request and
result are typed `MappingRequest` and `MappingReport` values.

The existing mapping command remains valid:

```text
python -m conversion_agent.mapping.cli INPUT OUTPUT [--rules FILE] [--llm]
```

Additive flags include `--project`, `--projects-root`, `--backend`, `--model`, and
`--debug`. `--project` supplies source-system context to the optional model lane;
it is not required for deterministic or backward-compatible standalone use. The
existing `--rules FILE` option remains the only source of project-specific token
maps in this refactor.

Workbook loading validates required `LookupSpec` and worksheet relationships,
section source/destination arity, destination pick lists, cascade maps, and source
rows before matching begins. Structural errors identify the workbook, sheet, and
section where possible.

Lane 1 remains deterministic and receives rule data explicitly. Lane 2 receives
an injected backend client and source-system description. Candidate lists and
batches are checked against configured limits before a model request. Every model
proposal still passes the same local validation gate as an externally supplied
proposal.

External proposal payloads receive schema validation before lookup. Duplicate
proposal keys, proposals for unknown sections or source rows, invalid confidence
values, wrong destination arity, pick-list violations, and cascade violations are
reported explicitly rather than silently overwritten or ignored.

Write-back follows these steps:

1. Resolve and validate input and output paths.
2. Refuse to overwrite the input workbook itself.
3. Write the modified package to a uniquely named sibling temporary file.
4. Reopen and verify the ZIP package, workbook relationships, edited cell values,
   hidden sheets, defined names, and data-validation extension presence.
5. Atomically replace the requested output path only after verification succeeds.
6. Remove the temporary file after either success or failure.

Human-entered destination cells remain protected unless the existing explicit
overwrite mode is selected. Reporting counts actual written destination and note
edits; a no-good-match proposal with no notes column is not reported as a written
mapping. Style-cloning failures are reported as warnings in `MappingReport` rather
than silently discarded, while successful value write-back may continue.

## 11. Errors and CLI Behavior

The shared error hierarchy distinguishes:

- Usage or settings errors: exit code 2.
- Project-not-found or project-validation errors: exit code 3.
- Workbook or proposal validation errors: exit code 4.
- Model-backend errors after bounded retry handling: exit code 5.
- Output or filesystem errors: exit code 6.

Default CLI output contains a concise summary, the offending path or field, and a
remediation hint. `--debug` enables the underlying traceback. Secrets, credentials,
and raw client records are not included in error messages.

Model retries are limited to transient transport, rate-limit, and server failures.
The default is two retries with backend-supported backoff. Validation,
authentication, and permission failures are not retried. Mapping produces no
final output after an unrecovered model or verification failure.

## 12. Packaging and Dependencies

The wheel includes shared knowledge and the DCT dictionary as package data. A
wheel smoke test installs the artifact into an isolated environment, changes to a
directory outside the checkout, loads the dictionary and shared knowledge, and
runs each console script's help command plus a project load through the public
repository API.

Default runtime dependencies cover both requested subsystems: Anthropic, PyYAML,
Pydantic, openpyxl, and lxml. DCT dictionary generation dependencies such as
python-docx live in a `dct-build` optional dependency group. Test, lint, formatting,
and type-check dependencies live in a `dev` group.

The package declares console scripts in addition to preserving all current
`python -m` entry points. Supported Python versions remain 3.11 and newer, with
continuous integration covering Python 3.11, 3.12, and 3.13.

## 13. Automated Verification

### Unit tests

- Configuration precedence and invalid setting values.
- Safe project identifiers, root containment, and symlink escape rejection.
- Project YAML, mapping CSV, and profile JSON validation.
- Mapping status normalization and immutable context behavior.
- Shared and project-overlay retrieval with citation scope.
- Dictionary caching and lookup behavior.
- Deterministic matching levels, ambiguity handling, cascades, and rule maps.
- External proposal schema and rejection reporting.
- CLI error rendering and exit-code mapping.

### Isolation tests

- Construct Project A and Project B sessions in the same process.
- Interleave tool calls and model turns.
- Assert that each session returns only its own mappings, profile, overlay
  knowledge, prompt context, and history.
- Construct sessions in parallel threads to ensure no shared active-project state
  remains.

### Workbook integration tests

Synthetic XLSX fixtures contain visible and hidden sheets, LookupSpec data,
defined names, styles, standard and extension-based validations, mapped human
cells, and empty destination cells. Tests verify deterministic and external
proposal application, cascade rejection, deliberate overwrite mode, exact trailing
spaces, preservation of protected workbook structures, atomic success, and cleanup
after injected failures.

### Distribution and compatibility tests

- Build and inspect the wheel for required resources.
- Install and run it outside the repository checkout.
- Run all existing module-based CLI forms with their current positional syntax.
- Load the current example project without adding a schema version.
- Confirm that missing optional project artifacts produce explicit empty-state
  responses instead of crashes.

### Model evaluation

Offline tests use fake structured responses to verify prompts, tool binding, and
proposal gates. Live Anthropic and Bedrock smoke tests are opt-in and marked so CI
does not run them without an explicitly configured environment. The existing SME
golden-question review remains a separate release-quality activity rather than a
deterministic unit-test gate.

## 14. Repository Hygiene and Documentation

- Ignore `.superpowers/`, Python build outputs, test caches, and platform metadata.
- Stop tracking `.DS_Store` without modifying unrelated user data.
- Update both READMEs with external-root configuration, project schema, optional
  overlay knowledge, additive CLI flags, dependency groups, and offline/live test
  commands.
- Document that real client artifacts remain outside Git and are transferred only
  through approved channels.
- Include an example schema-version-1 project and project-overlay knowledge file
  containing no confidential data.

## 15. Migration Sequence

1. Add characterization tests around current project loading, guidance prompts,
   deterministic mapping, proposal application, and workbook write-back.
2. Introduce settings, typed errors, project models, and the filesystem repository.
3. Move shared runtime data into package resources and add the resource catalog.
4. Replace global guidance tools with session-bound tools and bounded history.
5. Introduce mapping request/report types, validation, project-neutral prompts,
   and atomic verified write-back.
6. Route existing CLI modules through the new services and add only backward-
   compatible flags and console scripts.
7. Add wheel, isolation, integration, lint, type, and CI gates.
8. Update documentation and repository hygiene after all compatibility tests pass.

## 16. Acceptance Criteria

The refactor is complete when all of the following are true:

1. Two interleaved project sessions cannot access each other's context, knowledge,
   mapping rows, profile data, or history.
2. Current CLI commands and example-project usage still work.
3. An external project root works through both environment and CLI configuration.
4. Invalid projects and workbooks fail before model calls or output mutation, with
   actionable errors and stable exit codes.
5. Shared knowledge and the DCT dictionary load from an installed wheel outside
   the source checkout.
6. Optional project knowledge is retrieved only for its own project and is cited
   distinctly from shared knowledge.
7. Deterministic mapping and proposal validation remain model-independent.
8. Workbook outputs preserve human values and required workbook structures, and
   failed runs leave no partial final output.
9. The offline test suite, static checks, and Python 3.11–3.13 CI matrix pass
   without credentials.
10. Documentation explains the supported project layout, configuration precedence,
    compatibility behavior, and live-test opt-in process.
