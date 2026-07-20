# Scalable Shared-Core Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the guidance agent and mapping pipeline into a packaged, validated, project-isolated shared core while preserving all current CLI commands.

**Architecture:** Keep one `conversion_agent` distribution and introduce focused settings, project-repository, resource, guidance, mapping-service, and CLI boundaries. Project state is immutable and passed explicitly; shared resources may be cached, but client context and history never use process globals. Existing module commands become compatibility adapters over the new services.

**Tech Stack:** Python 3.11–3.13, dataclasses, Pydantic 2, PyYAML, Anthropic SDK, openpyxl, lxml, pytest, Ruff, mypy, setuptools, GitHub Actions.

## Global Constraints

- Preserve `python -m conversion_agent.cli PROJECT`, `python -m conversion_agent.mapping.cli INPUT OUTPUT [--rules FILE] [--llm]`, and `python -m conversion_agent.mapping.apply INPUT PROPOSALS OUTPUT`.
- Resolve the project root in this order: explicit argument, `CONVERSION_AGENT_PROJECTS_ROOT`, development fallback `agent/clients` when it exists.
- Preserve `project.yaml`, `mapping_workbook.csv`, and `profile_summary.json`; only `project.yaml` is required.
- Treat metadata without `schema_version` as schema version 1.
- Search shared knowledge plus only the active project's optional `knowledge/*.md` overlay.
- Do not introduce an HTTP service, hosted vector database, client-data migration, or credential-dependent default tests.
- Keep deterministic mapping model-independent and protect human-entered workbook cells unless explicit overwrite mode is requested.
- Build and test on Python 3.11, 3.12, and 3.13.
- Do not stage or overwrite the user's existing `.DS_Store` worktree modification.

---

## File Structure

### New application modules

- `agent/src/conversion_agent/core/settings.py`: immutable settings and precedence.
- `agent/src/conversion_agent/core/errors.py`: typed errors and stable CLI exit codes.
- `agent/src/conversion_agent/projects/models.py`: validated immutable project values.
- `agent/src/conversion_agent/projects/repository.py`: repository protocol.
- `agent/src/conversion_agent/projects/filesystem.py`: safe filesystem loader.
- `agent/src/conversion_agent/resources/catalog.py`: packaged shared-resource access and caching.
- `agent/src/conversion_agent/resources/knowledge.py`: shared/project knowledge indexes and citations.
- `agent/src/conversion_agent/guidance/backends.py`: injectable Anthropic and Bedrock factories.
- `agent/src/conversion_agent/guidance/tools.py`: project-bound tool construction.
- `agent/src/conversion_agent/guidance/session.py`: bounded session and tool-runner loop.
- `agent/src/conversion_agent/guidance/service.py`: repository-to-session orchestration.
- `agent/src/conversion_agent/mapping/validation.py`: workbook/proposal validation.
- `agent/src/conversion_agent/mapping/service.py`: typed mapping request/report orchestration.
- `agent/src/conversion_agent/cli/common.py`: parser helpers and error rendering.
- `agent/src/conversion_agent/cli/guidance.py`: guidance command adapter.
- `agent/src/conversion_agent/cli/mapping.py`: mapping command adapter.
- `agent/src/conversion_agent/cli/apply.py`: proposal-application command adapter.

### Compatibility and existing modules to modify

- `agent/src/conversion_agent/agent.py`: compatibility `ConversionAgent` over `GuidanceSession`.
- `agent/src/conversion_agent/backend.py`: compatibility facade over injected backend settings.
- `agent/src/conversion_agent/cli.py`: existing module-command wrapper.
- `agent/src/conversion_agent/config.py`: compatibility exports for project loading.
- `agent/src/conversion_agent/knowledge.py`: compatibility exports for shared search.
- `agent/src/conversion_agent/tools.py`: compatibility exports with no global project setter.
- `agent/src/conversion_agent/mapping/cli.py`: existing module-command wrapper.
- `agent/src/conversion_agent/mapping/apply.py`: validation-backed compatibility API and wrapper.
- `agent/src/conversion_agent/mapping/llm.py`: injected backend and source-neutral prompt.
- `agent/src/conversion_agent/mapping/workbook.py`: structural validation hooks.
- `agent/src/conversion_agent/mapping/writeback.py`: atomic write and verification.
- `agent/pyproject.toml`: dependencies, package data, scripts, and tool configuration.
- `.gitignore`: generated output, `.superpowers/`, test caches, and platform metadata.

### Runtime resources

- Move `agent/dct/dictionary.yaml` to `agent/src/conversion_agent/resources/data/dct/dictionary.yaml`.
- Move `agent/knowledge/**` to `agent/src/conversion_agent/resources/data/knowledge/**`.
- Keep `agent/dct/build_dictionary.py`, but write to the packaged dictionary path.
- Replace duplicate runtime playbook copies with links in repository documentation to the canonical packaged corpus.

### Tests and automation

- `agent/tests/conftest.py`: isolated project and workbook fixture factories.
- `agent/tests/core/test_settings.py`
- `agent/tests/projects/test_filesystem_repository.py`
- `agent/tests/resources/test_knowledge.py`
- `agent/tests/guidance/test_session_isolation.py`
- `agent/tests/guidance/test_tools.py`
- `agent/tests/mapping/test_validation.py`
- `agent/tests/mapping/test_service.py`
- `agent/tests/mapping/test_writeback.py`
- `agent/tests/cli/test_compatibility.py`
- `agent/tests/distribution/test_wheel.py`
- `.github/workflows/test.yml`

---

### Task 1: Establish the Offline Quality Harness

**Files:**
- Modify: `.gitignore`
- Modify: `agent/pyproject.toml`
- Create: `agent/tests/conftest.py`
- Create: `agent/tests/test_current_behavior.py`

**Interfaces:**
- Consumes: existing `conversion_agent.config.load_project`, `Matcher`, and `ProjectContext`.
- Produces: `pytest` configuration, the `example_project_root` fixture, and baseline characterization tests used throughout the refactor.

- [ ] **Step 1: Add behavior characterization tests**

```python
# agent/tests/test_current_behavior.py
from conversion_agent.config import load_project
from conversion_agent.mapping.match import Matcher


def test_example_project_and_matcher_baseline() -> None:
    project = load_project("example-client")
    assert project.mapping_status_counts == {
        "confirmed": 5,
        "blocked-on-config": 3,
        "draft": 2,
    }
    assert Matcher().norm("1C-ELEC", 3) == "commercial electrical"
```

- [ ] **Step 2: Run the characterization test before changing behavior**

Run: `cd agent && python -m pytest tests/test_current_behavior.py -v`

Expected: PASS with the current example-project counts and normalization behavior.

- [ ] **Step 3: Declare complete runtime/dev dependencies and repository ignores**

```toml
# Add to agent/pyproject.toml
[project]
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.92.0",
    "pydantic>=2.8,<3",
    "pyyaml>=6.0",
    "openpyxl>=3.1,<4",
    "lxml>=5,<7",
]

[project.optional-dependencies]
dct-build = ["python-docx>=1.1,<2"]
dev = [
    "build>=1.2,<2",
    "mypy>=1.10,<2",
    "pytest>=8,<9",
    "ruff>=0.12,<1",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live: requires a configured Anthropic or Bedrock backend"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.mypy]
python_version = "3.11"
packages = ["conversion_agent"]
```

```gitignore
# Add to .gitignore
.DS_Store
.superpowers/
.pytest_cache/
.mypy_cache/
.ruff_cache/
build/
dist/
```

- [ ] **Step 4: Add reusable project fixtures**

```python
# agent/tests/conftest.py
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    project = root / "alpha"
    project.mkdir(parents=True)
    (project / "project.yaml").write_text(
        yaml.safe_dump({
            "client_name": "Alpha City",
            "source_system": "Legacy Alpha",
            "phase": "Mock 1",
            "in_scope_entities": ["permits"],
        }),
        encoding="utf-8",
    )
    with (project / "mapping_workbook.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "source_table", "source_column", "target_table", "target_column",
            "rule", "status", "owner",
        ])
        writer.writeheader()
        writer.writerow({
            "source_table": "PERMITS", "source_column": "TYPE",
            "target_table": "permit", "target_column": "permit_type",
            "rule": "crosswalk", "status": "draft", "owner": "analyst",
        })
    (project / "profile_summary.json").write_text(
        json.dumps({"entities": {"permits": {"row_count": 10}}}), encoding="utf-8"
    )
    return root
```

- [ ] **Step 5: Run the baseline suite and commit**

Run: `cd agent && python -m pytest tests/test_current_behavior.py -v`

Expected: PASS.

```bash
git add .gitignore agent/pyproject.toml agent/tests
git commit -m "test: establish offline quality harness"
```

---

### Task 2: Add Typed Settings, Errors, and Project Loading

**Files:**
- Create: `agent/src/conversion_agent/core/__init__.py`
- Create: `agent/src/conversion_agent/core/settings.py`
- Create: `agent/src/conversion_agent/core/errors.py`
- Create: `agent/src/conversion_agent/projects/__init__.py`
- Create: `agent/src/conversion_agent/projects/models.py`
- Create: `agent/src/conversion_agent/projects/repository.py`
- Create: `agent/src/conversion_agent/projects/filesystem.py`
- Modify: `agent/src/conversion_agent/config.py`
- Create: `agent/tests/core/test_settings.py`
- Create: `agent/tests/projects/test_filesystem_repository.py`

**Interfaces:**
- Consumes: `project_root` fixture from Task 1.
- Produces: `AppSettings.from_sources(...)`, `ProjectRepository.load(project_id)`, `FilesystemProjectRepository`, immutable `ProjectContext`, `ProjectError`, and `ProjectValidationError`.

- [ ] **Step 1: Write failing settings and repository tests**

```python
# agent/tests/core/test_settings.py
from pathlib import Path

import pytest

from conversion_agent.core.errors import SettingsError
from conversion_agent.core.settings import AppSettings


def test_explicit_project_root_wins_over_environment(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    env = tmp_path / "env"
    settings = AppSettings.from_sources(
        projects_root=explicit,
        environ={"CONVERSION_AGENT_PROJECTS_ROOT": str(env)},
        development_root=None,
    )
    assert settings.projects_root == explicit.resolve()
    assert settings.max_history_messages == 40
    assert settings.max_tool_chars == 50_000


def test_rejects_nonpositive_history_limit(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="max_history_messages"):
        AppSettings.from_sources(
            projects_root=tmp_path,
            environ={"CONVERSION_AGENT_MAX_HISTORY_MESSAGES": "0"},
        )
```

```python
# agent/tests/projects/test_filesystem_repository.py
import pytest

from conversion_agent.core.errors import ProjectValidationError
from conversion_agent.projects.filesystem import FilesystemProjectRepository


def test_loads_legacy_v1_project_as_immutable_context(project_root) -> None:
    context = FilesystemProjectRepository(project_root).load("alpha")
    assert context.project_id == "alpha"
    assert context.metadata.schema_version == 1
    assert context.metadata.client_name == "Alpha City"
    assert context.mapping_status_counts == {"draft": 1}
    assert isinstance(context.mapping_rows, tuple)


@pytest.mark.parametrize("project_id", ["../alpha", "/tmp/alpha", ".alpha", "a/b", ""])
def test_rejects_unsafe_project_identifiers(project_root, project_id) -> None:
    with pytest.raises(ProjectValidationError):
        FilesystemProjectRepository(project_root).load(project_id)
```

- [ ] **Step 2: Run the tests and verify import failures**

Run: `cd agent && python -m pytest tests/core tests/projects -v`

Expected: FAIL because the `core` and `projects` packages do not exist.

- [ ] **Step 3: Implement immutable settings and typed errors**

```python
# agent/src/conversion_agent/core/errors.py
class ConversionAgentError(Exception):
    exit_code = 1


class SettingsError(ConversionAgentError):
    exit_code = 2


class ProjectError(ConversionAgentError):
    exit_code = 3


class ProjectValidationError(ProjectError):
    pass


class WorkbookError(ConversionAgentError):
    exit_code = 4


class BackendError(ConversionAgentError):
    exit_code = 5


class OutputError(ConversionAgentError):
    exit_code = 6
```

```python
# agent/src/conversion_agent/core/settings.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AppSettings:
    projects_root: Path | None
    backend: str = "anthropic"
    model: str = "claude-opus-4-8"
    max_history_messages: int = 40
    max_tool_chars: int = 50_000
    mapping_default_limit: int = 100
    mapping_max_limit: int = 500
    backend_retries: int = 2

    def __post_init__(self) -> None:
        from .errors import SettingsError
        for name in (
            "max_history_messages", "max_tool_chars", "mapping_default_limit",
            "mapping_max_limit",
        ):
            if getattr(self, name) <= 0:
                raise SettingsError(f"{name} must be greater than zero")
        if self.mapping_default_limit > self.mapping_max_limit:
            raise SettingsError("mapping_default_limit cannot exceed mapping_max_limit")

    @classmethod
    def from_sources(
        cls,
        *,
        projects_root: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
        development_root: Path | None = None,
        require_projects: bool = True,
    ) -> "AppSettings":
        env = dict(environ or {})
        root_value = projects_root or env.get("CONVERSION_AGENT_PROJECTS_ROOT") or development_root
        if root_value is None and require_projects:
            from .errors import SettingsError
            raise SettingsError("Set --projects-root or CONVERSION_AGENT_PROJECTS_ROOT.")
        try:
            numeric = {
                "max_history_messages": int(env.get("CONVERSION_AGENT_MAX_HISTORY_MESSAGES", "40")),
                "max_tool_chars": int(env.get("CONVERSION_AGENT_MAX_TOOL_CHARS", "50000")),
                "mapping_default_limit": int(env.get("CONVERSION_AGENT_MAPPING_DEFAULT_LIMIT", "100")),
                "mapping_max_limit": int(env.get("CONVERSION_AGENT_MAPPING_MAX_LIMIT", "500")),
            }
        except ValueError as exc:
            from .errors import SettingsError
            raise SettingsError(f"Invalid integer setting: {exc}") from exc
        return cls(
            projects_root=Path(root_value).expanduser().resolve() if root_value else None,
            backend=env.get("CONVERSION_AGENT_BACKEND", "anthropic").lower(),
            model=env.get("CONVERSION_AGENT_MODEL", "claude-opus-4-8"),
            **numeric,
        )
```

- [ ] **Step 4: Implement project models and repository protocol**

```python
# agent/src/conversion_agent/projects/repository.py
from typing import Protocol

from .models import ProjectContext


class ProjectRepository(Protocol):
    def load(self, project_id: str) -> ProjectContext: ...
```

```python
# agent/src/conversion_agent/projects/models.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ProjectMetadata:
    schema_version: int
    client_name: str
    source_system: str
    phase: str
    in_scope_entities: tuple[str, ...]
    conversion_lead: str | None
    client_data_steward: str | None
    extras: Mapping[str, Any]


@dataclass(frozen=True)
class MappingRow:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    rule: str
    status: str
    owner: str


@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    root: Path
    metadata: ProjectMetadata
    mapping_rows: tuple[MappingRow, ...]
    profile_summary: Mapping[str, Any]
    knowledge_dir: Path | None

    @property
    def mapping_status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.mapping_rows:
            key = row.status.strip().lower() or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return counts


def freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    return value
```

- [ ] **Step 5: Implement safe filesystem validation**

```python
# agent/src/conversion_agent/projects/filesystem.py
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from conversion_agent.core.errors import ProjectError, ProjectValidationError
from .models import MappingRow, ProjectContext, ProjectMetadata, freeze_json

PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
MAPPING_FIELDS = tuple(MappingRow.__dataclass_fields__)


class _ProjectDocument(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: int = Field(default=1, ge=1)
    client_name: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    in_scope_entities: list[str] = Field(min_length=1)
    conversion_lead: str | None = None
    client_data_steward: str | None = None


class FilesystemProjectRepository:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()

    def load(self, project_id: str) -> ProjectContext:
        if not PROJECT_ID.fullmatch(project_id):
            raise ProjectValidationError(f"Unsafe project identifier: {project_id!r}")
        project_dir = (self.root / project_id).resolve()
        if project_dir.parent != self.root:
            raise ProjectValidationError("Project path escapes the configured projects root.")
        project_file = project_dir / "project.yaml"
        if not project_file.is_file():
            raise ProjectError(f"Missing project file: {project_file}")
        try:
            raw = yaml.safe_load(project_file.read_text(encoding="utf-8"))
            doc = _ProjectDocument.model_validate(raw)
        except (OSError, yaml.YAMLError, ValidationError) as exc:
            raise ProjectValidationError(f"Invalid {project_file}: {exc}") from exc
        extras = doc.model_extra or {}
        metadata = ProjectMetadata(
            schema_version=doc.schema_version,
            client_name=doc.client_name.strip(),
            source_system=doc.source_system.strip(),
            phase=doc.phase.strip(),
            in_scope_entities=tuple(dict.fromkeys(x.strip() for x in doc.in_scope_entities if x.strip())),
            conversion_lead=doc.conversion_lead,
            client_data_steward=doc.client_data_steward,
            extras=freeze_json(extras),
        )
        rows = self._load_mapping(project_dir / "mapping_workbook.csv")
        profile = self._load_profile(project_dir / "profile_summary.json")
        knowledge_dir = project_dir / "knowledge"
        return ProjectContext(
            project_id=project_id,
            root=project_dir,
            metadata=metadata,
            mapping_rows=rows,
            profile_summary=freeze_json(profile),
            knowledge_dir=knowledge_dir if knowledge_dir.is_dir() else None,
        )

    def _load_mapping(self, path: Path) -> tuple[MappingRow, ...]:
        if not path.exists():
            return ()
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != MAPPING_FIELDS:
                raise ProjectValidationError(f"Invalid mapping headers in {path}")
            return tuple(MappingRow(**{name: row[name] for name in MAPPING_FIELDS}) for row in reader)

    def _load_profile(self, path: Path) -> dict:
        if not path.exists():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("entities", {}), dict):
            raise ProjectValidationError(f"Profile must be an object with object-valued entities: {path}")
        return value
```

- [ ] **Step 6: Preserve the old configuration API**

```python
# agent/src/conversion_agent/config.py
from pathlib import Path

from .core.settings import AppSettings
from .projects.filesystem import FilesystemProjectRepository
from .projects.models import ProjectContext

AGENT_ROOT = Path(__file__).resolve().parents[2]
CLIENTS_DIR = AGENT_ROOT / "clients"


def load_project(client_name: str, projects_root: Path | str | None = None) -> ProjectContext:
    settings = AppSettings.from_sources(
        projects_root=projects_root,
        environ=__import__("os").environ,
        development_root=CLIENTS_DIR if CLIENTS_DIR.is_dir() else None,
    )
    return FilesystemProjectRepository(settings.projects_root).load(client_name)
```

- [ ] **Step 7: Run tests and commit**

Run: `cd agent && python -m pytest tests/core tests/projects tests/test_current_behavior.py::test_example_project_and_matcher_baseline -v`

Expected: PASS.

```bash
git add agent/src/conversion_agent/core agent/src/conversion_agent/projects agent/src/conversion_agent/config.py agent/tests/core agent/tests/projects
git commit -m "feat: validate and isolate project configuration"
```

---

### Task 3: Package Shared Resources and Merge Project Knowledge

**Files:**
- Create: `agent/src/conversion_agent/resources/__init__.py`
- Create: `agent/src/conversion_agent/resources/catalog.py`
- Create: `agent/src/conversion_agent/resources/knowledge.py`
- Move: `agent/dct/dictionary.yaml` → `agent/src/conversion_agent/resources/data/dct/dictionary.yaml`
- Move: `agent/knowledge/**` → `agent/src/conversion_agent/resources/data/knowledge/**`
- Modify: `agent/dct/build_dictionary.py`
- Modify: `agent/src/conversion_agent/knowledge.py`
- Modify: `agent/src/conversion_agent/config.py`
- Modify: `agent/pyproject.toml`
- Create: `agent/tests/resources/test_knowledge.py`

**Interfaces:**
- Consumes: `ProjectContext.knowledge_dir` from Task 2.
- Produces: `ResourceCatalog.dictionary()`, `ResourceCatalog.shared_knowledge()`, `KnowledgeIndex.for_project(...)`, and scoped `Chunk.citation`.

- [ ] **Step 1: Write failing shared/overlay isolation tests**

```python
# agent/tests/resources/test_knowledge.py
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog
from conversion_agent.resources.knowledge import KnowledgeIndex


def test_project_overlay_is_scoped_and_cited(project_root) -> None:
    overlay = project_root / "alpha" / "knowledge"
    overlay.mkdir()
    (overlay / "alpha-rule.md").write_text(
        "# Alpha rule\n\nUse ALPHA-ONLY disposition.", encoding="utf-8"
    )
    project = FilesystemProjectRepository(project_root).load("alpha")
    index = KnowledgeIndex.for_project(ResourceCatalog().shared_knowledge(), project)
    hit = index.search("ALPHA-ONLY", top_k=1)[0]
    assert hit.scope == "project"
    assert hit.citation == "[project source: alpha/knowledge/alpha-rule.md § Alpha rule]"


def test_dictionary_is_cached_and_contains_release_metadata() -> None:
    catalog = ResourceCatalog()
    first = catalog.dictionary()
    second = catalog.dictionary()
    assert first is second
    assert first["version"] == "V2025.2.01"
    assert first["table_count"] == 309
```

- [ ] **Step 2: Run tests and verify missing-module failures**

Run: `cd agent && python -m pytest tests/resources -v`

Expected: FAIL because resource modules do not exist.

- [ ] **Step 3: Move canonical resources and declare package data**

```bash
mkdir -p agent/src/conversion_agent/resources/data/dct
git mv agent/dct/dictionary.yaml agent/src/conversion_agent/resources/data/dct/dictionary.yaml
git mv agent/knowledge agent/src/conversion_agent/resources/data/knowledge
```

```toml
# agent/pyproject.toml
[tool.setuptools.package-data]
"conversion_agent.resources" = [
    "data/dct/*.yaml",
    "data/knowledge/**/*.md",
]
```

- [ ] **Step 4: Implement the shared resource catalog**

```python
# agent/src/conversion_agent/resources/catalog.py
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

import yaml

from conversion_agent.projects.models import freeze_json
from .knowledge import KnowledgeIndex


def _root():
    return files("conversion_agent.resources").joinpath("data")


@lru_cache(maxsize=1)
def _dictionary():
    raw = yaml.safe_load(_root().joinpath("dct/dictionary.yaml").read_text(encoding="utf-8"))
    return freeze_json(raw)


@lru_cache(maxsize=1)
def _shared_knowledge() -> KnowledgeIndex:
    return KnowledgeIndex.from_traversable(_root().joinpath("knowledge"), scope="shared")


class ResourceCatalog:
    def dictionary(self):
        return _dictionary()

    def shared_knowledge(self) -> KnowledgeIndex:
        return _shared_knowledge()
```

- [ ] **Step 5: Implement scoped retrieval**

```python
# agent/src/conversion_agent/resources/knowledge.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Chunk:
    source: str
    heading: str
    text: str
    scope: str
    project_id: str | None = None
    score: float = 0.0

    @property
    def citation(self) -> str:
        if self.scope == "project":
            return f"[project source: {self.project_id}/{self.source} § {self.heading}]"
        return f"[source: {self.source} § {self.heading}]"


class KnowledgeIndex:
    def __init__(self, chunks: Iterable[Chunk]):
        self.chunks = tuple(chunks)

    @classmethod
    def for_project(cls, shared: "KnowledgeIndex", project) -> "KnowledgeIndex":
        chunks = list(shared.chunks)
        if project.knowledge_dir:
            chunks.extend(
                cls.from_path(project.knowledge_dir, project.root, project.project_id).chunks
            )
        return cls(chunks)

    @classmethod
    def from_traversable(cls, root, scope: str = "shared") -> "KnowledgeIndex":
        chunks: list[Chunk] = []
        for item, relative in _walk_traversable(root):
            if item.is_file() and relative.endswith(".md"):
                chunks.extend(_chunks(relative, item.read_text(encoding="utf-8"), scope))
        return cls(chunks)

    @classmethod
    def from_path(cls, knowledge_dir: Path, project_root: Path, project_id: str) -> "KnowledgeIndex":
        project_root = project_root.resolve()
        chunks: list[Chunk] = []
        for path in sorted(knowledge_dir.rglob("*.md")):
            resolved = path.resolve()
            if project_root not in resolved.parents:
                raise ValueError(f"Project knowledge path escapes project root: {path}")
            source = resolved.relative_to(project_root).as_posix()
            chunks.extend(_chunks(source, resolved.read_text(encoding="utf-8"), "project", project_id))
        return cls(chunks)

    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        terms = set(_WORD.findall(query.lower()))
        scored = []
        for chunk in self.chunks:
            section_terms = set(_WORD.findall(f"{chunk.heading} {chunk.text}".lower()))
            overlap = terms & section_terms
            if overlap:
                scored.append(Chunk(**{**chunk.__dict__, "score": len(overlap) / len(terms)}))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def _walk_traversable(root, prefix: str = ""):
    for item in root.iterdir():
        relative = f"{prefix}/{item.name}" if prefix else item.name
        if item.is_dir():
            yield from _walk_traversable(item, relative)
        else:
            yield item, relative


def _chunks(source: str, text: str, scope: str, project_id: str | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading = Path(source).stem
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            body = "\n".join(lines).strip()
            if body:
                chunks.append(Chunk(source, heading, body, scope, project_id))
            heading = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)
    body = "\n".join(lines).strip()
    if body:
        chunks.append(Chunk(source, heading, body, scope, project_id))
    return chunks
```

- [ ] **Step 6: Update compatibility loaders and dictionary builder**

```python
# agent/src/conversion_agent/config.py compatibility function
from .resources.catalog import ResourceCatalog


def load_dictionary():
    return ResourceCatalog().dictionary()
```

```python
# agent/dct/build_dictionary.py destination
dest = (
    Path(__file__).resolve().parents[1]
    / "src/conversion_agent/resources/data/dct/dictionary.yaml"
)
```

- [ ] **Step 7: Run resource and baseline tests, then commit**

Run: `cd agent && python -m pytest tests/resources tests/test_current_behavior.py -v`

Expected: PASS, including dictionary metadata and project-overlay isolation.

```bash
git add agent/src/conversion_agent/resources agent/src/conversion_agent/knowledge.py agent/src/conversion_agent/config.py agent/dct agent/pyproject.toml agent/tests/resources
git commit -m "feat: package shared resources and project knowledge"
```

---

### Task 4: Replace Global Guidance State with Isolated Sessions

**Files:**
- Create: `agent/src/conversion_agent/guidance/__init__.py`
- Create: `agent/src/conversion_agent/guidance/backends.py`
- Create: `agent/src/conversion_agent/guidance/tools.py`
- Create: `agent/src/conversion_agent/guidance/session.py`
- Create: `agent/src/conversion_agent/guidance/service.py`
- Modify: `agent/src/conversion_agent/agent.py`
- Modify: `agent/src/conversion_agent/backend.py`
- Modify: `agent/src/conversion_agent/tools.py`
- Create: `agent/tests/guidance/test_tools.py`
- Create: `agent/tests/guidance/test_backends.py`
- Create: `agent/tests/guidance/test_session_isolation.py`

**Interfaces:**
- Consumes: `AppSettings`, `ProjectRepository`, `ProjectContext`, `ResourceCatalog`, and `KnowledgeIndex`.
- Produces: `build_tools(context, index, dictionary, settings)`, `GuidanceSession.ask(question)`, `GuidanceService.open_session(project_id)`, and compatible `ConversionAgent(project)`.

- [ ] **Step 1: Write failing tool/session isolation tests**

```python
# agent/tests/guidance/test_session_isolation.py
from concurrent.futures import ThreadPoolExecutor

from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.service import GuidanceService
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog


class FakeBackendFactory:
    model_id = "fake-model"

    def create(self):
        return object()


def test_two_sessions_keep_project_tools_isolated(two_project_root) -> None:
    settings = AppSettings(projects_root=two_project_root)
    service = GuidanceService(
        settings,
        FilesystemProjectRepository(two_project_root),
        ResourceCatalog(),
        FakeBackendFactory(),
    )
    alpha = service.open_session("alpha")
    beta = service.open_session("beta")
    with ThreadPoolExecutor(max_workers=2) as pool:
        alpha_json, beta_json = list(pool.map(
            lambda session: session.call_tool("get_mapping_status", {}),
            (alpha, beta),
        ))
    assert "Alpha City" in alpha_json and "Beta City" not in alpha_json
    assert "Beta City" in beta_json and "Alpha City" not in beta_json
```

```python
# agent/tests/guidance/test_tools.py
import json


def test_mapping_tool_is_bounded(bound_tool_set) -> None:
    result = json.loads(bound_tool_set.call("get_mapping_status", {"limit": 1, "offset": 0}))
    assert result["returned"] == 1
    assert result["truncated"] is True
```

```python
# agent/tests/guidance/test_backends.py
import pytest

from conversion_agent.guidance.backends import run_with_retries


class TransientFailure(Exception):
    pass


def test_transient_backend_operation_gets_two_retries() -> None:
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientFailure("try again")
        return "ok"

    result = run_with_retries(
        operation,
        retries=2,
        is_transient=lambda exc: isinstance(exc, TransientFailure),
        sleep=lambda _: None,
    )
    assert result == "ok"
    assert attempts == 3


def test_nontransient_backend_operation_is_not_retried() -> None:
    attempts = 0

    def operation():
        nonlocal attempts
        attempts += 1
        raise PermissionError("denied")

    with pytest.raises(PermissionError):
        run_with_retries(operation, retries=2, is_transient=lambda _: False, sleep=lambda _: None)
    assert attempts == 1
```

- [ ] **Step 2: Run tests and verify missing-module failures**

Run: `cd agent && python -m pytest tests/guidance -v`

Expected: FAIL because the guidance package does not exist.

- [ ] **Step 3: Implement injected backends**

```python
# agent/src/conversion_agent/guidance/backends.py
from __future__ import annotations

import os
import time
from typing import Protocol

import anthropic

from conversion_agent.core.settings import AppSettings


class ModelBackendFactory(Protocol):
    def create(self): ...


class AnthropicBackendFactory:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def create(self):
        if self.settings.backend == "bedrock":
            from anthropic import AnthropicBedrockMantle
            return AnthropicBedrockMantle(aws_region=os.environ.get("AWS_REGION", "us-east-1"))
        return anthropic.Anthropic()

    @property
    def model_id(self) -> str:
        prefix = "anthropic." if self.settings.backend == "bedrock" else ""
        return f"{prefix}{self.settings.model}"


def is_transient_backend_error(exc: Exception) -> bool:
    return isinstance(exc, (
        anthropic.APIConnectionError,
        anthropic.RateLimitError,
        anthropic.InternalServerError,
    ))


def run_with_retries(operation, *, retries: int, is_transient=is_transient_backend_error, sleep=time.sleep):
    for attempt in range(retries + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == retries or not is_transient(exc):
                raise
            sleep(2 ** attempt)
    raise AssertionError("retry loop exited unexpectedly")
```

- [ ] **Step 4: Implement a project-bound tool factory**

```python
# agent/src/conversion_agent/guidance/tools.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Mapping

from anthropic import beta_tool


@dataclass(frozen=True)
class BoundToolSet:
    anthropic_tools: tuple
    handlers: Mapping[str, Callable[..., str]]

    def call(self, name: str, arguments: dict) -> str:
        return self.handlers[name](**arguments)


def build_tools(project, knowledge_index, dictionary, settings) -> BoundToolSet:
    def search_knowledge_base(query: str) -> str:
        hits = knowledge_index.search(query)
        if not hits:
            return "No knowledge-base results. Say you don't know and escalate."
        return "\n\n---\n\n".join(f"{hit.citation}\n{hit.text}" for hit in hits)[: settings.max_tool_chars]

    def get_mapping_status(status_filter: str = "", limit: int = 100, offset: int = 0) -> str:
        limit = max(1, min(limit, settings.mapping_max_limit))
        rows = [row for row in project.mapping_rows if not status_filter or row.status.strip().lower() == status_filter.strip().lower()]
        page = rows[offset : offset + limit]
        payload = {
            "client": project.metadata.client_name,
            "status_counts": project.mapping_status_counts,
            "offset": offset,
            "returned": len(page),
            "total": len(rows),
            "truncated": offset + len(page) < len(rows),
            "rows": [row.__dict__ for row in page],
        }
        return json.dumps(payload, indent=2)[: settings.max_tool_chars]

    def lookup_dct_field(table: str = "", column: str = "", module: str = "") -> str:
        tables = dictionary.get("tables", {})
        if module and not table:
            hits = {
                name: entry.get("description", "")
                for name, entry in tables.items()
                if entry.get("module") == module.strip().lower()
            }
            value = {"module": module, "tables": hits}
        else:
            key = table.strip().lower()
            entry = tables.get(key)
            if entry is None:
                near = [name for name in tables if key and key in name]
                return f"Table '{table}' not in dictionary. Close matches: {near[:15]}"
            if column:
                col_key = column.strip().lower()
                col = entry.get("columns", {}).get(col_key)
                if col is None:
                    return f"Column '{column}' not in {key}."
                value = {"table": key, "column": col_key, **col}
            else:
                value = {"table": key, **entry}
        return json.dumps(value, indent=2)[: settings.max_tool_chars]

    def get_profile_summary(entity: str = "") -> str:
        profile = project.profile_summary
        if not profile:
            return "No profiling summary loaded for this client yet."
        if entity:
            entities = profile.get("entities", {})
            match = entities.get(entity.lower())
            if match is None:
                return f"No profile for entity '{entity}'. Known: {sorted(entities)}"
            profile = {entity.lower(): match}
        return json.dumps(profile, indent=2)[: settings.max_tool_chars]

    handlers = {
        "search_knowledge_base": search_knowledge_base,
        "lookup_dct_field": lookup_dct_field,
        "get_mapping_status": get_mapping_status,
        "get_profile_summary": get_profile_summary,
    }
    decorated = tuple(
        beta_tool(handler)
        for handler in handlers.values()
    )
    return BoundToolSet(decorated, handlers)
```

- [ ] **Step 5: Implement bounded sessions and service orchestration**

```python
# agent/src/conversion_agent/guidance/session.py
CORE_PROMPT = """You are the Conversion Guidance Agent for EPL implementation teams.
Ground every substantive claim in a tool result and cite knowledge sources and DCT fields.
If tools do not support an answer, say you do not know and escalate to the Conversion Lead.
Recommend changes as drafts; never claim to have changed client data.
Keep answers practical and specific to the active project's context.
"""


def build_system(project: ProjectContext) -> list[dict]:
    metadata = project.metadata
    project_block = (
        "Current project context:\n"
        f"- Client: {metadata.client_name}\n"
        f"- Legacy source: {metadata.source_system}\n"
        f"- Phase: {metadata.phase}\n"
        f"- Mapping status counts: {project.mapping_status_counts}\n"
        f"- In-scope entities: {list(metadata.in_scope_entities)}\n"
    )
    return [
        {"type": "text", "text": CORE_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": project_block},
    ]


class GuidanceSession:
    def __init__(self, *, project, client, model_id, tools, settings, system):
        self.project = project
        self.client = client
        self.model_id = model_id
        self.tools = tools
        self.settings = settings
        self.system = system
        self.history: list[dict] = []

    def _trim_history(self) -> None:
        while len(self.history) > self.settings.max_history_messages:
            del self.history[:2]

    def ask(self, question: str) -> str:
        self.history.append({"role": "user", "content": question})
        self._trim_history()
        runner = self.client.beta.messages.tool_runner(
            model=self.model_id,
            max_tokens=16_000,
            thinking={"type": "adaptive"},
            system=self.system,
            tools=self.tools.anthropic_tools,
            messages=self.history,
        )
        final = run_with_retries(
            runner.until_done,
            retries=self.settings.backend_retries,
        )
        answer = "".join(block.text for block in final.content if block.type == "text")
        self.history.append({"role": "assistant", "content": answer})
        self._trim_history()
        return answer

    def call_tool(self, name: str, arguments: dict) -> str:
        return self.tools.call(name, arguments)
```

```python
# agent/src/conversion_agent/guidance/service.py
class GuidanceService:
    def __init__(self, settings, repository, catalog, backend_factory):
        self.settings = settings
        self.repository = repository
        self.catalog = catalog
        self.backend_factory = backend_factory

    def open_session(self, project_id: str):
        project = self.repository.load(project_id)
        index = KnowledgeIndex.for_project(self.catalog.shared_knowledge(), project)
        tools = build_tools(project, index, self.catalog.dictionary(), self.settings)
        return GuidanceSession(
            project=project,
            client=self.backend_factory.create(),
            model_id=self.backend_factory.model_id,
            tools=tools,
            settings=self.settings,
            system=build_system(project),
        )
```

- [ ] **Step 6: Remove the global setter and retain `ConversionAgent` compatibility**

```python
# agent/src/conversion_agent/agent.py
class ConversionAgent(GuidanceSession):
    """Backward-compatible project-scoped session constructor."""

    def __init__(self, project: ProjectContext, settings: AppSettings | None = None):
        settings = settings or AppSettings.from_sources(
            projects_root=project.root.parent,
            environ=os.environ,
            development_root=None,
        )
        catalog = ResourceCatalog()
        factory = AnthropicBackendFactory(settings)
        index = KnowledgeIndex.for_project(catalog.shared_knowledge(), project)
        super().__init__(
            project=project,
            client=factory.create(),
            model_id=factory.model_id,
            tools=build_tools(project, index, catalog.dictionary(), settings),
            settings=settings,
            system=build_system(project),
        )
```

Replace `conversion_agent.tools` with explicit compatibility exports; the absence
of `_project`, `set_project`, and `_require_project` is enforced by the isolation
tests:

```python
# agent/src/conversion_agent/tools.py
from .guidance.tools import BoundToolSet, build_tools

__all__ = ["BoundToolSet", "build_tools"]
```

- [ ] **Step 7: Run guidance isolation tests and commit**

Run: `cd agent && python -m pytest tests/guidance -v`

Expected: PASS, including parallel Project A/Project B isolation.

```bash
git add agent/src/conversion_agent/guidance agent/src/conversion_agent/agent.py agent/src/conversion_agent/backend.py agent/src/conversion_agent/tools.py agent/tests/guidance
git commit -m "refactor: isolate guidance sessions by project"
```

---

### Task 5: Validate Mapping Requests and External Proposals

**Files:**
- Create: `agent/src/conversion_agent/mapping/validation.py`
- Create: `agent/src/conversion_agent/mapping/service.py`
- Modify: `agent/src/conversion_agent/mapping/apply.py`
- Modify: `agent/src/conversion_agent/mapping/llm.py`
- Modify: `agent/src/conversion_agent/mapping/workbook.py`
- Create: `agent/tests/mapping/test_validation.py`
- Create: `agent/tests/mapping/test_service.py`

**Interfaces:**
- Consumes: existing `CrosswalkWorkbook`, `Proposal`, matcher, parser, and backend factory.
- Produces: `ProposalDocument`, `MappingRequest`, `MappingReport`, `validate_proposals(model, payload)`, and `MappingService.run(request)`.

- [ ] **Step 1: Write failing proposal and prompt-neutrality tests**

```python
# agent/tests/mapping/test_validation.py
import openpyxl
import pytest

from conversion_agent.core.errors import WorkbookError
from conversion_agent.mapping.validation import validate_proposal_document
from conversion_agent.mapping.validation import load_validated_workbook


def test_rejects_duplicate_proposal_keys() -> None:
    payload = {"proposals": [
        {"tab": "Permits", "section": "Type", "source": ["A"], "dest": ["One"], "confidence": 0.8, "rationale": "first"},
        {"tab": "Permits", "section": "Type", "source": ["A"], "dest": ["Two"], "confidence": 0.7, "rationale": "second"},
    ]}
    with pytest.raises(WorkbookError, match="duplicate"):
        validate_proposal_document(payload)


def test_rejects_workbook_without_lookup_spec(tmp_path) -> None:
    path = tmp_path / "invalid.xlsx"
    openpyxl.Workbook().save(path)
    with pytest.raises(WorkbookError, match="LookupSpec"):
        load_validated_workbook(path)
```

```python
# agent/tests/mapping/test_service.py
from conversion_agent.mapping.llm import build_system_prompt


def test_model_prompt_is_source_neutral_without_project() -> None:
    prompt = build_system_prompt(None)
    assert "legacy system" in prompt
    assert "New World" not in prompt


def test_model_prompt_uses_project_source_system() -> None:
    prompt = build_system_prompt("Legacy Alpha")
    assert "Legacy Alpha" in prompt
```

- [ ] **Step 2: Run tests and verify missing APIs**

Run: `cd agent && python -m pytest tests/mapping/test_validation.py tests/mapping/test_service.py -v`

Expected: FAIL because validation and service APIs do not exist.

- [ ] **Step 3: Implement typed proposal validation**

```python
# agent/src/conversion_agent/mapping/validation.py
import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from conversion_agent.core.errors import WorkbookError
from . import workbook


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tab: str = Field(min_length=1)
    section: str = Field(min_length=1)
    source: tuple[str, ...] = Field(min_length=1)
    dest: tuple[str, ...] | None
    confidence: float = Field(default=0.7, ge=0, le=1)
    rationale: str = ""


class ProposalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposals: tuple[ProposalInput, ...]


def validate_proposal_document(payload: object) -> ProposalDocument:
    try:
        document = ProposalDocument.model_validate(payload)
    except ValidationError as exc:
        raise WorkbookError(f"Invalid proposal document: {exc}") from exc
    seen = set()
    for proposal in document.proposals:
        key = (proposal.tab, proposal.section, proposal.source)
        if key in seen:
            raise WorkbookError(f"Duplicate proposal key: {key}")
        seen.add(key)
    return document


def load_validated_workbook(path):
    try:
        model = workbook.load(str(path))
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise WorkbookError(f"Invalid workbook {path}: {exc}") from exc
    if not model.spec:
        raise WorkbookError(f"Workbook {path} has no valid LookupSpec contract")
    if not model.sections:
        raise WorkbookError(f"Workbook {path} has no mapping sections")
    for section in model.sections:
        if not section.src_cols or not section.dst_cols:
            raise WorkbookError(f"Section {section.key} has invalid source/destination arity")
        if len(section.dest_lists) < len(section.dst_cols):
            raise WorkbookError(f"Section {section.key} is missing destination pick lists")
        if len(section.dst_cols) == 2 and section.cascade:
            invalid = set(section.cascade) - set(section.dest_lists[0])
            if invalid:
                raise WorkbookError(f"Section {section.key} has invalid cascade keys: {sorted(invalid)}")
    return model
```

- [ ] **Step 4: Make external application report unknown and rejected proposals**

```python
# agent/src/conversion_agent/mapping/apply.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ProposalRejection:
    source: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ProposalApplicationReport:
    accepted: tuple[ProposalInput, ...]
    no_match: tuple[ProposalInput, ...]
    rejected: tuple[ProposalRejection, ...]


def apply(model, proposals: ProposalDocument) -> ProposalApplicationReport:
    accepted: list[ProposalInput] = []
    no_match: list[ProposalInput] = []
    rejected: list[ProposalRejection] = []
    sections = {(section.tab, section.title): section for section in model.sections}
    for proposal in proposals.proposals:
        section = sections.get((proposal.tab, proposal.section))
        if section is None:
            rejected.append(ProposalRejection(proposal.source, "unknown section"))
            continue
        rows = [row for row in section.rows if row.values == proposal.source]
        if not rows:
            rejected.append(ProposalRejection(proposal.source, "unknown source row"))
            continue
        for row in rows:
            if any(value.strip() for value in row.existing) or row.row_idx in section.proposals:
                rejected.append(ProposalRejection(proposal.source, "already mapped"))
                continue
            if proposal.dest is None:
                section.proposals[row.row_idx] = Proposal(
                    dest=tuple("" for _ in section.dst_cols),
                    method="llm",
                    confidence=proposal.confidence,
                    note=f"NO GOOD MATCH — {proposal.rationale[:180]}",
                )
                no_match.append(proposal)
                continue
            if len(proposal.dest) != len(section.dst_cols):
                rejected.append(ProposalRejection(proposal.source, "wrong destination arity"))
                continue
            if not section.dest_lists or not all(
                value in valid for value, valid in zip(proposal.dest, section.dest_lists)
            ):
                rejected.append(ProposalRejection(proposal.source, "value not in pick list"))
                continue
            if (
                len(proposal.dest) == 2
                and section.cascade
                and proposal.dest[1] not in section.cascade.get(proposal.dest[0], [])
            ):
                rejected.append(ProposalRejection(proposal.source, "cascade violation"))
                continue
            section.proposals[row.row_idx] = Proposal(
                dest=proposal.dest,
                method="llm",
                confidence=proposal.confidence,
                note=f"proposed ({proposal.confidence:.0%}): {proposal.rationale[:180]}",
            )
            accepted.append(proposal)
    return ProposalApplicationReport(tuple(accepted), tuple(no_match), tuple(rejected))
```

- [ ] **Step 5: Inject source-system context into Lane 2**

```python
# agent/src/conversion_agent/mapping/llm.py
def build_system_prompt(source_system: str | None) -> str:
    source = source_system.strip() if source_system else "a legacy system"
    return f"""You map legacy lookup values from {source} to configured EPL values.

Rules:
- Choose destination values ONLY from the provided candidate list.
- Expand abbreviations and reason about the source meaning without assuming a specific vendor.
- If no candidate is a faithful semantic match, use no_good_match.
- Report calibrated confidence: 0.9+ only when the meaning is unambiguous.
"""


def run(
    section,
    *,
    client,
    model_id: str,
    source_system: str | None = None,
    retries: int = 2,
) -> None:
    if not section.dest_lists or len(section.dst_cols) != 1:
        return
    candidates = section.dest_lists[0]
    pending = section.unmatched
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        sources = [" | ".join(value for value in row.values if value) for row in batch]
        response = run_with_retries(
            lambda: client.messages.parse(
                model=model_id,
                max_tokens=16_000,
                system=build_system_prompt(source_system),
                output_config={"format": {"type": "json_schema", "schema": _schema(candidates)}},
                messages=[{
                    "role": "user",
                    "content": (
                        f"Section: {section.key}\nCandidate destination values:\n"
                        + "\n".join(f"- {candidate}" for candidate in candidates)
                        + "\n\nMap each legacy value:\n"
                        + "\n".join(f"- {source}" for source in sources)
                    ),
                }],
            ),
            retries=retries,
        )
        result = response.parsed_output
        if result is None:
            continue
        by_source = {mapping["source"]: mapping for mapping in result["mappings"]}
        for row, source in zip(batch, sources):
            mapping = by_source.get(source)
            if not mapping or mapping["match"] is None or mapping["confidence"] < MIN_CONFIDENCE:
                continue
            section.proposals[row.row_idx] = Proposal(
                dest=(mapping["match"],),
                method="llm",
                confidence=float(mapping["confidence"]),
                note=f"proposed ({mapping['confidence']:.0%}): {mapping['rationale'][:160]}",
            )
```

- [ ] **Step 6: Implement mapping service request/report orchestration**

```python
# agent/src/conversion_agent/mapping/service.py
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MappingRequest:
    input_path: Path
    output_path: Path
    token_map: dict[str, str] = field(default_factory=dict)
    use_llm: bool = False
    project_id: str | None = None
    overwrite: bool = False


@dataclass(frozen=True)
class MappingReport:
    rows: int
    premapped: int
    deterministic: int
    model_proposed: int
    remaining: int
    warnings: tuple[str, ...] = ()


class MappingService:
    def __init__(self, *, repository=None, backend_factory=None):
        self.repository = repository
        self.backend_factory = backend_factory

    def run(self, request: MappingRequest) -> MappingReport:
        model = load_validated_workbook(request.input_path)
        project = self.repository.load(request.project_id) if request.project_id else None
        for section in model.sections:
            match.run(section, token_map=request.token_map)
        if request.use_llm:
            client = self.backend_factory.create()
            for section in model.sections:
                llm.run(
                    section,
                    client=client,
                    model_id=self.backend_factory.model_id,
                    source_system=project.metadata.source_system if project else None,
                    retries=self.backend_factory.settings.backend_retries,
                )
        written = writeback.write(model, str(request.output_path), overwrite=request.overwrite)
        return build_report(model, written)
```

- [ ] **Step 7: Run mapping validation/service tests and commit**

Run: `cd agent && python -m pytest tests/mapping/test_validation.py tests/mapping/test_service.py -v`

Expected: PASS with fake model clients only.

```bash
git add agent/src/conversion_agent/mapping agent/tests/mapping/test_validation.py agent/tests/mapping/test_service.py
git commit -m "refactor: validate and orchestrate mapping requests"
```

---

### Task 6: Make Workbook Write-Back Atomic and Verifiable

**Files:**
- Modify: `agent/src/conversion_agent/mapping/writeback.py`
- Modify: `agent/src/conversion_agent/mapping/model.py`
- Create: `agent/tests/mapping/test_writeback.py`

**Interfaces:**
- Consumes: validated `CrosswalkWorkbook` and proposals from Task 5.
- Produces: `WriteReport`, `verify_output(source, output, expected_edits)`, atomic `write(...)`, and style warnings surfaced to `MappingReport`.

- [ ] **Step 1: Write failing atomicity and preservation tests**

```python
# agent/tests/mapping/test_writeback.py
from pathlib import Path

import pytest

from conversion_agent.core.errors import OutputError
from conversion_agent.mapping import workbook, writeback


def test_write_refuses_input_as_output(crosswalk_path: Path) -> None:
    model = workbook.load(str(crosswalk_path))
    with pytest.raises(OutputError, match="input workbook"):
        writeback.write(model, str(crosswalk_path))


def test_failed_verification_keeps_existing_output(monkeypatch, mapped_model, tmp_path) -> None:
    output = tmp_path / "out.xlsx"
    output.write_bytes(b"existing")
    monkeypatch.setattr(writeback, "verify_output", lambda *args, **kwargs: (_ for _ in ()).throw(OutputError("bad workbook")))
    with pytest.raises(OutputError):
        writeback.write(mapped_model, str(output))
    assert output.read_bytes() == b"existing"
    assert not list(tmp_path.glob(".out.xlsx.*.tmp"))
```

- [ ] **Step 2: Run tests and confirm they fail against direct output writes**

Run: `cd agent && python -m pytest tests/mapping/test_writeback.py -v`

Expected: FAIL because input/output equality and atomic verification are not implemented.

- [ ] **Step 3: Add typed write reporting**

```python
# agent/src/conversion_agent/mapping/model.py
@dataclass(frozen=True)
class WriteReport:
    deterministic_rows: int
    model_rows: int
    destination_cells: int
    note_cells: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CellEdit:
    sheet_path: str
    cell_ref: str
    value: str
```

- [ ] **Step 4: Implement sibling-temp write and atomic replacement**

```python
# core control flow in mapping/writeback.py
import os
import tempfile
from pathlib import Path

from conversion_agent.core.errors import OutputError


def write(model, out_path: str, overwrite: bool = False) -> WriteReport:
    source = Path(model.path).resolve()
    output = Path(out_path).resolve()
    if source == output:
        raise OutputError("Output path must not be the input workbook.")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(fd)
    temporary = Path(tmp_name)
    try:
        report, expected_edits = _write_package(model, temporary, overwrite=overwrite)
        verify_output(source, temporary, expected_edits)
        os.replace(temporary, output)
        return report
    except OutputError:
        raise
    except Exception as exc:
        raise OutputError(f"Could not write verified workbook {output}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
```

- [ ] **Step 5: Verify workbook invariants and surface style warnings**

```python
def verify_output(source: Path, output: Path, expected_edits: tuple[CellEdit, ...]) -> None:
    with zipfile.ZipFile(source) as source_zip, zipfile.ZipFile(output) as output_zip:
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/styles.xml"}
        if not required <= set(output_zip.namelist()):
            raise OutputError("Output is missing required workbook package parts.")
        for name in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels"):
            if source_zip.read(name) != output_zip.read(name):
                raise OutputError(f"Protected workbook part changed unexpectedly: {name}")
        edits_by_sheet: dict[str, list[CellEdit]] = {}
        for edit in expected_edits:
            edits_by_sheet.setdefault(edit.sheet_path, []).append(edit)
        for sheet_path, edits in edits_by_sheet.items():
            source_root = etree.fromstring(source_zip.read(sheet_path))
            output_root = etree.fromstring(output_zip.read(sheet_path))
            source_ext = source_root.find(f"{{{NS_MAIN}}}extLst")
            output_ext = output_root.find(f"{{{NS_MAIN}}}extLst")
            source_ext_xml = b"" if source_ext is None else etree.tostring(source_ext)
            output_ext_xml = b"" if output_ext is None else etree.tostring(output_ext)
            if source_ext_xml != output_ext_xml:
                raise OutputError(f"Data-validation extensions changed: {sheet_path}")
            cells = {
                cell.get("r"): cell
                for cell in output_root.findall(f".//{{{NS_MAIN}}}c")
            }
            for edit in edits:
                cell = cells.get(edit.cell_ref)
                text = "" if cell is None else "".join(cell.itertext())
                if text != edit.value:
                    raise OutputError(
                        f"Expected {edit.sheet_path}!{edit.cell_ref}={edit.value!r}, got {text!r}"
                    )
```

Pass a mutable `warnings: list[str]` into `_set_cell`. Replace its broad style
exception handler with this exact behavior so value writes continue and the
warning reaches `WriteReport`:

```python
except Exception as exc:
    warnings.append(f"Style not applied to {ref}: {type(exc).__name__}: {exc}")
```

If `_StyleCloner` construction fails, append
`f"Style cloning disabled: {type(exc).__name__}: {exc}"`. Return
`WriteReport(..., warnings=tuple(warnings))` from `_write_package`.

- [ ] **Step 6: Run write-back and mapping regression tests, then commit**

Run: `cd agent && python -m pytest tests/mapping -v`

Expected: PASS, including atomic failure cleanup and protected workbook structures.

```bash
git add agent/src/conversion_agent/mapping/model.py agent/src/conversion_agent/mapping/writeback.py agent/tests/mapping
git commit -m "feat: verify workbook writes atomically"
```

---

### Task 7: Preserve Existing CLIs and Add Shared Configuration Flags

**Files:**
- Create: `agent/src/conversion_agent/cli/__init__.py`
- Create: `agent/src/conversion_agent/cli/common.py`
- Create: `agent/src/conversion_agent/cli/guidance.py`
- Create: `agent/src/conversion_agent/cli/mapping.py`
- Create: `agent/src/conversion_agent/cli/apply.py`
- Modify: `agent/src/conversion_agent/cli.py`
- Modify: `agent/src/conversion_agent/mapping/cli.py`
- Modify: `agent/src/conversion_agent/mapping/apply.py`
- Modify: `agent/pyproject.toml`
- Create: `agent/tests/cli/test_compatibility.py`

**Interfaces:**
- Consumes: settings/repository/guidance/mapping services from Tasks 2–6.
- Produces: `guidance_main(argv=None)`, `mapping_main(argv=None)`, `apply_main(argv=None)`, `render_error(error, debug=False)`, and console scripts.

- [ ] **Step 1: Write failing CLI compatibility tests**

```python
# agent/tests/cli/test_compatibility.py
from conversion_agent.cli.guidance import build_parser as guidance_parser
from conversion_agent.cli.mapping import build_parser as mapping_parser
from conversion_agent.cli.common import render_error
from conversion_agent.core.errors import ProjectValidationError


def test_guidance_keeps_project_positional_argument() -> None:
    args = guidance_parser().parse_args(["example-client"])
    assert args.project == "example-client"


def test_mapping_keeps_existing_positional_and_flags() -> None:
    args = mapping_parser().parse_args(["in.xlsx", "out.xlsx", "--rules", "rules.yaml", "--llm"])
    assert args.input == "in.xlsx"
    assert args.output == "out.xlsx"
    assert args.rules == "rules.yaml"
    assert args.llm is True


def test_new_project_root_flag_is_additive() -> None:
    args = guidance_parser().parse_args(["alpha", "--projects-root", "/projects"])
    assert args.projects_root == "/projects"


def test_project_error_uses_stable_exit_code(capsys) -> None:
    code = render_error(ProjectValidationError("bad project"))
    assert code == 3
    assert "bad project" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests and verify missing CLI package failures**

Run: `cd agent && python -m pytest tests/cli -v`

Expected: FAIL because the adapter package does not exist.

- [ ] **Step 3: Implement common error rendering**

```python
# agent/src/conversion_agent/cli/common.py
import traceback

from conversion_agent.core.errors import ConversionAgentError


def render_error(error: Exception, *, debug: bool = False) -> int:
    if debug:
        traceback.print_exception(error)
    else:
        print(f"error: {error}", file=__import__("sys").stderr)
    return error.exit_code if isinstance(error, ConversionAgentError) else 1
```

- [ ] **Step 4: Implement parsers and adapters without changing old syntax**

```python
# agent/src/conversion_agent/cli/guidance.py
import argparse
import os
from pathlib import Path

from .common import render_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conversion-agent")
    parser.add_argument("project")
    parser.add_argument("--projects-root")
    parser.add_argument("--backend", choices=("anthropic", "bedrock"))
    parser.add_argument("--model")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        return render_error(exc, debug=args.debug)


def _run(args) -> int:
    env = dict(os.environ)
    if args.backend:
        env["CONVERSION_AGENT_BACKEND"] = args.backend
    if args.model:
        env["CONVERSION_AGENT_MODEL"] = args.model
    settings = AppSettings.from_sources(
        projects_root=args.projects_root,
        environ=env,
        development_root=development_clients_root(),
    )
    service = GuidanceService(
        settings,
        FilesystemProjectRepository(settings.projects_root),
        ResourceCatalog(),
        AnthropicBackendFactory(settings),
    )
    session = service.open_session(args.project)
    return run_interactive(session)
```

```python
# agent/src/conversion_agent/cli/mapping.py
import argparse
import os
from pathlib import Path

import yaml

from .common import render_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conversion-map")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--rules")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--project")
    parser.add_argument("--projects-root")
    parser.add_argument("--backend", choices=("anthropic", "bedrock"))
    parser.add_argument("--model")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        return render_error(exc, debug=args.debug)


def _run(args) -> int:
    env = dict(os.environ)
    if args.backend:
        env["CONVERSION_AGENT_BACKEND"] = args.backend
    if args.model:
        env["CONVERSION_AGENT_MODEL"] = args.model
    settings = AppSettings.from_sources(
        projects_root=args.projects_root,
        environ=env,
        development_root=development_clients_root(),
        require_projects=bool(args.project),
    )
    repository = (
        FilesystemProjectRepository(settings.projects_root)
        if args.project and settings.projects_root
        else None
    )
    rules = yaml.safe_load(Path(args.rules).read_text(encoding="utf-8")) if args.rules else {}
    service = MappingService(
        repository=repository,
        backend_factory=AnthropicBackendFactory(settings) if args.llm else None,
    )
    report = service.run(MappingRequest(
        input_path=Path(args.input),
        output_path=Path(args.output),
        token_map=(rules or {}).get("token_map", {}),
        use_llm=args.llm,
        project_id=args.project,
    ))
    print(format_mapping_report(report))
    return 0
```

```python
# agent/src/conversion_agent/cli/apply.py
import argparse
import json
from pathlib import Path

from .common import render_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conversion-apply")
    parser.add_argument("input")
    parser.add_argument("proposals")
    parser.add_argument("output")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        return render_error(exc, debug=args.debug)


def _run(args) -> int:
    model = workbook.load(args.input)
    payload = json.loads(Path(args.proposals).read_text(encoding="utf-8"))
    application = apply(model, validate_proposal_document(payload))
    write_report = writeback.write(model, args.output, overwrite=args.overwrite)
    print(json.dumps({
        "accepted": len(application.accepted),
        "no_good_match": len(application.no_match),
        "rejected": [rejection.__dict__ for rejection in application.rejected],
        "written": write_report.__dict__,
    }, indent=2, default=list))
    return 0
```

- [ ] **Step 5: Replace old modules with thin wrappers and declare scripts**

```python
# agent/src/conversion_agent/cli.py
from .cli.guidance import main


if __name__ == "__main__":
    raise SystemExit(main())
```

```toml
# agent/pyproject.toml
[project.scripts]
conversion-agent = "conversion_agent.cli.guidance:main"
conversion-map = "conversion_agent.cli.mapping:main"
conversion-apply = "conversion_agent.cli.apply:main"
```

- [ ] **Step 6: Run CLI tests and help smoke tests, then commit**

Run: `cd agent && python -m pytest tests/cli -v`

Run: `cd agent && python -m conversion_agent.cli --help && python -m conversion_agent.mapping.cli --help && python -m conversion_agent.mapping.apply --help`

Expected: all tests pass and each command exits 0 with help text.

```bash
git add agent/src/conversion_agent/cli agent/src/conversion_agent/cli.py agent/src/conversion_agent/mapping/cli.py agent/src/conversion_agent/mapping/apply.py agent/pyproject.toml agent/tests/cli
git commit -m "feat: preserve and extend command line interfaces"
```

---

### Task 8: Prove the Installed Distribution and CI Matrix

**Files:**
- Create: `agent/tests/distribution/test_wheel.py`
- Create: `.github/workflows/test.yml`
- Modify: `agent/pyproject.toml`

**Interfaces:**
- Consumes: packaged resources and console scripts from Tasks 3 and 7.
- Produces: reproducible build checks and Python 3.11–3.13 CI.

- [ ] **Step 1: Write a failing wheel-content test**

```python
# agent/tests/distribution/test_wheel.py
from pathlib import Path
from zipfile import ZipFile


def test_built_wheel_contains_runtime_resources(built_wheel: Path) -> None:
    with ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())
    assert "conversion_agent/resources/data/dct/dictionary.yaml" in names
    assert any(name.endswith("resources/data/knowledge/playbook/README.md") for name in names)
    metadata = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
    with ZipFile(built_wheel) as wheel:
        entry_points = wheel.read(metadata).decode()
    assert "conversion-agent" in entry_points
    assert "conversion-map" in entry_points
    assert "conversion-apply" in entry_points
```

- [ ] **Step 2: Run the distribution test and confirm any resource gaps**

Run: `cd agent && python -m pytest tests/distribution/test_wheel.py -v`

Expected: FAIL until the `built_wheel` fixture builds the artifact and all package-data patterns are correct.

- [ ] **Step 3: Add isolated wheel fixture and outside-checkout smoke test**

```python
# add to agent/tests/conftest.py
import subprocess
import sys
import sysconfig
import venv


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(out)], check=True)
    return next(out.glob("*.whl"))
```

```python
# agent/tests/distribution/test_wheel.py
import os
import subprocess
import sysconfig
import venv


def test_wheel_loads_resources_outside_checkout(built_wheel: Path, tmp_path: Path) -> None:
    environment = tmp_path / "venv"
    outside = tmp_path / "outside"
    outside.mkdir()
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(built_wheel)],
        check=True,
    )
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = sysconfig.get_paths()["purelib"]
    code = """
from conversion_agent.resources.catalog import ResourceCatalog
import conversion_agent
catalog = ResourceCatalog()
assert catalog.dictionary()["table_count"] == 309
assert "outside" not in str(conversion_agent.__file__)
print(conversion_agent.__file__)
"""
    result = subprocess.run(
        [str(python), "-c", code],
        cwd=outside,
        env=child_env,
        check=True,
        text=True,
        capture_output=True,
    )
    assert str(environment) in result.stdout
```

- [ ] **Step 4: Add the CI matrix**

```yaml
# .github/workflows/test.yml
name: test
on:
  pull_request:
  push:
    branches: [main]
jobs:
  quality:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: python -m pip install -e './agent[dev,dct-build]'
      - run: ruff check agent/src agent/tests agent/evals agent/dct
      - run: ruff format --check agent/src agent/tests agent/evals agent/dct
      - run: mypy agent/src
      - run: python -m pytest agent/tests -m 'not live' -v
      - run: python -m build --wheel agent
```

- [ ] **Step 5: Run all quality gates and commit**

Run: `cd agent && ruff check src tests evals dct`

Run: `cd agent && ruff format --check src tests evals dct`

Run: `cd agent && mypy src`

Run: `cd agent && python -m pytest tests -m 'not live' -v`

Run: `cd agent && python -m build --wheel --outdir dist`

Expected: all commands exit 0; the wheel test confirms runtime resources and scripts.

```bash
git add .github/workflows/test.yml agent/pyproject.toml agent/tests/distribution agent/tests/conftest.py
git commit -m "ci: verify package across supported Python versions"
```

---

### Task 9: Update Documentation, Evals, and Final Compatibility Evidence

**Files:**
- Modify: `README.md`
- Modify: `agent/README.md`
- Modify: `agent/clients/example-client/project.yaml`
- Create: `agent/clients/example-client/knowledge/example-project-rule.md`
- Modify: `agent/evals/run_evals.py`
- Modify: `agent/dct/build_dictionary.py`
- Remove from Git index: `.DS_Store` while leaving the user's filesystem copy untouched

**Interfaces:**
- Consumes: final CLI, project schema, resource layout, and test commands.
- Produces: complete operator guidance and final acceptance evidence.

- [ ] **Step 1: Write failing documentation/example checks**

```python
# agent/tests/test_documentation_examples.py
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_example_project_declares_schema_v1() -> None:
    project = yaml.safe_load((ROOT / "agent/clients/example-client/project.yaml").read_text())
    assert project["schema_version"] == 1


def test_readme_documents_external_project_root_and_offline_tests() -> None:
    text = (ROOT / "agent/README.md").read_text(encoding="utf-8")
    assert "CONVERSION_AGENT_PROJECTS_ROOT" in text
    assert "knowledge/" in text
    assert "pytest tests -m 'not live'" in text
```

- [ ] **Step 2: Run checks and verify they fail on missing documentation**

Run: `cd agent && python -m pytest tests/test_documentation_examples.py -v`

Expected: FAIL until the example schema version and README sections are added.

- [ ] **Step 3: Update example data and documentation**

```yaml
# first line of agent/clients/example-client/project.yaml
schema_version: 1
```

Document these exact workflows in `agent/README.md`:

```bash
export CONVERSION_AGENT_PROJECTS_ROOT=/approved/path/to/projects
conversion-agent example-client
conversion-map input.xlsx output.xlsx --project example-client --llm
python -m pytest tests -m 'not live' -v
python -m pytest -m live -v  # only in an explicitly configured environment
```

Document the required/optional project layout and distinct shared versus
`[project source: ...]` citations. Update the root README's quick start and package
layout to match the canonical resources.

- [ ] **Step 4: Route evals through settings/repository/service APIs**

```python
# agent/evals/run_evals.py core construction
settings = AppSettings.from_sources(
    projects_root=args.projects_root,
    environ=os.environ,
    development_root=Path(__file__).resolve().parents[1] / "clients",
)
service = GuidanceService(
    settings,
    FilesystemProjectRepository(settings.projects_root),
    ResourceCatalog(),
    AnthropicBackendFactory(settings),
)
for question in spec["questions"]:
    session = service.open_session(args.client)
    answer = session.ask(question["question"])
```

- [ ] **Step 5: Stop tracking platform metadata without deleting the user's copy**

Run: `git rm --cached .DS_Store`

Expected: Git stages deletion from the repository; the local `.DS_Store` file remains present and ignored.

- [ ] **Step 6: Run final acceptance suite**

Run: `cd agent && ruff check src tests evals dct`

Run: `cd agent && ruff format --check src tests evals dct`

Run: `cd agent && mypy src`

Run: `cd agent && python -m pytest tests -m 'not live' -v`

Run: `cd agent && python -m build --wheel --outdir dist`

Run: `git diff --check`

Expected: all commands exit 0; no live credentials are used; `git status --short` contains only intentional refactor changes and no `.superpowers/`, build, cache, or platform files.

- [ ] **Step 7: Commit documentation and cleanup**

```bash
git add README.md agent/README.md agent/clients/example-client agent/evals/run_evals.py agent/dct/build_dictionary.py agent/tests/test_documentation_examples.py .gitignore
git commit -m "docs: document scalable project workflows"
```

- [ ] **Step 8: Record final verification evidence**

Run: `git log --oneline --decorate -10`

Run: `git status --short --branch`

Expected: the feature branch contains the design, plan, and task commits; the worktree is clean; every acceptance criterion in `docs/superpowers/specs/2026-07-20-scalable-shared-core-refactor-design.md` has corresponding passing evidence above.
