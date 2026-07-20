import json
import csv
from pathlib import Path

import pytest
import yaml

from conversion_agent.agent import build_system
from conversion_agent.core.settings import AppSettings
from conversion_agent.core.errors import ProjectValidationError
from conversion_agent.guidance.tools import build_tools
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog
from conversion_agent.resources.knowledge import KnowledgeIndex


MAPPING_HEADERS = [
    "source_table",
    "source_column",
    "target_table",
    "target_column",
    "rule",
    "status",
    "owner",
]


def test_loads_legacy_v1_project_as_immutable_context(project_root) -> None:
    context = FilesystemProjectRepository(project_root).load("alpha")
    assert context.project_id == "alpha"
    assert context.metadata.schema_version == 1
    assert context.metadata.client_name == "Alpha City"
    assert context.mapping_status_counts == {"draft": 1}
    assert isinstance(context.mapping_rows, tuple)


def test_loaded_context_supports_current_agent_and_mapping_tool_consumers(project_root) -> None:
    context = FilesystemProjectRepository(project_root).load("alpha")
    catalog = ResourceCatalog()
    tools = build_tools(
        context,
        KnowledgeIndex.for_project(catalog.shared_knowledge(), context),
        catalog.dictionary(),
        AppSettings(projects_root=project_root),
    )

    assert context.name == "alpha"
    assert context.project["client_name"] == "Alpha City"
    assert "Alpha City" in build_system(context)[1]["text"]

    result = json.loads(tools.call("get_mapping_status", {"status_filter": "draft"}))
    assert result == {
        "client": "Alpha City",
        "status_counts": {"draft": 1},
        "offset": 0,
        "returned": 1,
        "total": 1,
        "truncated": False,
        "rows": [
            {
                "source_table": "PERMITS",
                "source_column": "TYPE",
                "target_table": "permit",
                "target_column": "permit_type",
                "rule": "crosswalk",
                "status": "draft",
                "owner": "analyst",
            }
        ],
    }


def test_loaded_context_serializes_frozen_profile_through_current_tool(project_root) -> None:
    profile_file = project_root / "alpha" / "profile_summary.json"
    profile_file.write_text(
        json.dumps(
            {
                "entities": {
                    "permits": {
                        "row_count": 10,
                        "notes": ["legacy values", "validated"],
                        "metrics": {"null_rate": 0.1},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    context = FilesystemProjectRepository(project_root).load("alpha")
    catalog = ResourceCatalog()
    tools = build_tools(
        context,
        KnowledgeIndex.for_project(catalog.shared_knowledge(), context),
        catalog.dictionary(),
        AppSettings(projects_root=project_root),
    )

    assert json.loads(tools.call("get_profile_summary", {})) == {
        "entities": {
            "permits": {
                "row_count": 10,
                "notes": ["legacy values", "validated"],
                "metrics": {"null_rate": 0.1},
            }
        }
    }
    assert json.loads(tools.call("get_profile_summary", {"entity": "permits"})) == {
        "permits": {
            "row_count": 10,
            "notes": ["legacy values", "validated"],
            "metrics": {"null_rate": 0.1},
        }
    }


@pytest.mark.parametrize("project_id", ["../alpha", "/tmp/alpha", ".alpha", "a/b", ""])
def test_rejects_unsafe_project_identifiers(project_root, project_id) -> None:
    with pytest.raises(ProjectValidationError):
        FilesystemProjectRepository(project_root).load(project_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("client_name", "  "),
        ("source_system", "  "),
        ("phase", "  "),
        ("in_scope_entities", ["permits", "  "]),
    ],
)
def test_rejects_whitespace_only_metadata_values(project_root, field, value) -> None:
    project_file = project_root / "alpha" / "project.yaml"
    document = yaml.safe_load(project_file.read_text(encoding="utf-8"))
    document[field] = value
    project_file.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(ProjectValidationError):
        FilesystemProjectRepository(project_root).load("alpha")


@pytest.mark.parametrize(
    "entities",
    [
        ["permits", "permits"],
        [" permits ", "permits"],
        ["PERMITS", "permits"],
    ],
)
def test_rejects_duplicate_normalized_in_scope_entities(project_root, entities) -> None:
    project_file = project_root / "alpha" / "project.yaml"
    document = yaml.safe_load(project_file.read_text(encoding="utf-8"))
    document["in_scope_entities"] = entities
    project_file.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(ProjectValidationError, match=r"project.yaml.*in_scope_entities"):
        FilesystemProjectRepository(project_root).load("alpha")


@pytest.mark.parametrize(
    "artifact", ["project.yaml", "mapping_workbook.csv", "profile_summary.json"]
)
def test_rejects_non_utf8_project_artifacts(project_root: Path, artifact: str) -> None:
    (project_root / "alpha" / artifact).write_bytes(b"\xff")

    with pytest.raises(ProjectValidationError):
        FilesystemProjectRepository(project_root).load("alpha")


@pytest.mark.parametrize(
    ("headers", "row"),
    [
        (MAPPING_HEADERS, ["PERMITS", "TYPE", "permit", "permit_type", "crosswalk", "draft"]),
        (
            MAPPING_HEADERS,
            [
                "PERMITS",
                "TYPE",
                "permit",
                "permit_type",
                "crosswalk",
                "draft",
                "analyst",
                "extra value",
            ],
        ),
        (
            MAPPING_HEADERS,
            ["PERMITS", "", "permit", "permit_type", "crosswalk", "draft", "analyst"],
        ),
        (MAPPING_HEADERS[:-1], ["PERMITS", "TYPE", "permit", "permit_type", "crosswalk", "draft"]),
    ],
    ids=["short-row-none", "extra-cell", "blank-required-value", "header-width-mismatch"],
)
def test_rejects_malformed_mapping_rows(project_root: Path, headers, row) -> None:
    mapping_file = project_root / "alpha" / "mapping_workbook.csv"
    with mapping_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerow(row)

    with pytest.raises(ProjectValidationError):
        FilesystemProjectRepository(project_root).load("alpha")


def test_resolves_knowledge_directory_within_project(project_root: Path) -> None:
    knowledge_dir = project_root / "alpha" / "knowledge"
    knowledge_dir.mkdir()

    context = FilesystemProjectRepository(project_root).load("alpha")

    assert context.knowledge_dir == knowledge_dir.resolve()


def test_rejects_knowledge_directory_symlink_that_escapes_project(project_root: Path) -> None:
    outside_dir = project_root.parent / "outside-knowledge"
    outside_dir.mkdir()
    knowledge_dir = project_root / "alpha" / "knowledge"
    try:
        knowledge_dir.symlink_to(outside_dir, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    with pytest.raises(ProjectValidationError, match="knowledge"):
        FilesystemProjectRepository(project_root).load("alpha")
