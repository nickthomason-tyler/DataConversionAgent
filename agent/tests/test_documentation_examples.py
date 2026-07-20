"""Regression checks for the documented, safe example project workflow."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import yaml

from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog
from conversion_agent.resources.knowledge import KnowledgeIndex


ROOT = Path(__file__).parents[2]


def test_example_project_declares_schema_v1_and_safe_overlay() -> None:
    project_file = ROOT / "agent/clients/example-client/project.yaml"
    project = yaml.safe_load(project_file.read_text())
    overlay = ROOT / "agent/clients/example-client/knowledge/example-project-rule.md"

    assert project["schema_version"] == 1
    assert overlay.is_file()
    assert "Exampleton" in overlay.read_text(encoding="utf-8")

    context = FilesystemProjectRepository(project_file.parent.parent).load("example-client")
    index = KnowledgeIndex.for_project(ResourceCatalog().shared_knowledge(), context)
    overlay_chunk = next(
        chunk for chunk in index.search("Exampleton sequencing") if chunk.scope == "project"
    )
    shared_chunk = next(
        chunk
        for chunk in index.search("sentinel date handling")
        if chunk.source == "decisions/sentinel-dates.md" and chunk.scope == "shared"
    )

    assert overlay_chunk.citation == (
        "[project source: example-client/knowledge/example-project-rule.md "
        "§ Exampleton business-license sequencing]"
    )
    assert shared_chunk.citation == ("[source: decisions/sentinel-dates.md § Decision]")


def test_readmes_document_external_projects_and_offline_tests() -> None:
    agent_readme = (ROOT / "agent/README.md").read_text(encoding="utf-8")
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "export CONVERSION_AGENT_PROJECTS_ROOT=/approved/path/to/projects" in agent_readme
    assert "conversion-agent example-client" in agent_readme
    assert "conversion-map input.xlsx output.xlsx --project example-client --llm" in agent_readme
    assert "python -m pytest tests -m 'not live' -v" in agent_readme
    assert "python -m pytest -m live -v" in agent_readme
    assert (
        "ANTHROPIC_API_KEY=... python -m pytest tests/guidance/test_live_smoke.py -m live -v"
    ) in agent_readme
    assert (
        "CONVERSION_AGENT_LIVE_BEDROCK=1 CONVERSION_AGENT_BACKEND=bedrock "
        "AWS_REGION=us-east-1 python -m pytest tests/guidance/test_live_smoke.py -m live -v"
    ) in agent_readme
    assert (
        "`--projects-root` takes precedence over `CONVERSION_AGENT_PROJECTS_ROOT`, which\n"
        "takes precedence over the source-checkout example project."
    ) in agent_readme
    assert "An installed wheel\nhas no fallback client storage" in agent_readme
    assert "[project source: <project-id>/<path> § <heading>]" in agent_readme
    assert "conversion-agent example-client" in root_readme
    assert "agent/src/conversion_agent/resources/data/" in root_readme


def test_eval_runner_opens_a_fresh_service_session_per_question(
    monkeypatch, tmp_path: Path
) -> None:
    module_path = ROOT / "agent/evals/run_evals.py"
    spec = importlib.util.spec_from_file_location("run_evals", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "build_service"), "eval runner must construct GuidanceService explicitly"

    captured: dict[str, object] = {}

    class FakeSettings:
        @classmethod
        def from_sources(cls, **kwargs):
            captured["settings"] = kwargs
            return SimpleNamespace(projects_root=Path("/approved/projects"))

    class FakeRepository:
        def __init__(self, root):
            captured["projects_root"] = root

    class FakeFactory:
        def __init__(self, settings):
            captured["factory_settings"] = settings

    class FakeSession:
        def ask(self, question: str) -> str:
            return f"answer: {question}"

    class FakeService:
        def __init__(self, settings, repository, catalog, factory):
            captured["service"] = (settings, repository, catalog, factory)
            self.projects: list[str] = []
            captured["service_instance"] = self

        def open_session(self, project_id: str) -> FakeSession:
            self.projects.append(project_id)
            return FakeSession()

    monkeypatch.setattr(module, "AppSettings", FakeSettings)
    monkeypatch.setattr(module, "FilesystemProjectRepository", FakeRepository)
    monkeypatch.setattr(module, "AnthropicBackendFactory", FakeFactory)
    monkeypatch.setattr(module, "GuidanceService", FakeService)
    monkeypatch.setattr(module, "ResourceCatalog", lambda: "catalog")
    monkeypatch.setattr(module, "EVALS_DIR", tmp_path)
    (tmp_path / "golden_questions.yaml").write_text(
        yaml.safe_dump(
            {
                "questions": [
                    {"id": "one", "question": "first", "must_contain": []},
                    {"id": "two", "question": "second", "must_contain": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert module.main(["example-client", "--projects-root", "/approved/projects"]) == 0
    assert captured["settings"] == {
        "projects_root": "/approved/projects",
        "environ": module.os.environ,
        "development_root": ROOT / "agent/clients",
    }
    assert captured["projects_root"] == Path("/approved/projects")
    service = captured["service"]
    assert isinstance(service, tuple)
    instance = captured["service_instance"]
    assert isinstance(instance, FakeService)
    assert instance.projects == ["example-client", "example-client"]
    assert (tmp_path / "results.md").read_text(encoding="utf-8").count("answer:") == 2
