import json
from pathlib import Path

import pytest
import yaml

from conversion_agent.agent import build_system
from conversion_agent.core.errors import ProjectValidationError
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.tools import get_mapping_status, set_project


def test_loads_legacy_v1_project_as_immutable_context(project_root) -> None:
    context = FilesystemProjectRepository(project_root).load("alpha")
    assert context.project_id == "alpha"
    assert context.metadata.schema_version == 1
    assert context.metadata.client_name == "Alpha City"
    assert context.mapping_status_counts == {"draft": 1}
    assert isinstance(context.mapping_rows, tuple)


def test_loaded_context_supports_current_agent_and_mapping_tool_consumers(project_root) -> None:
    context = FilesystemProjectRepository(project_root).load("alpha")

    assert context.name == "alpha"
    assert context.project["client_name"] == "Alpha City"
    assert "Alpha City" in build_system(context)[1]["text"]

    set_project(context)
    result = json.loads(get_mapping_status.func(status_filter="draft"))
    assert result == {
        "client": "alpha",
        "status_counts": {"draft": 1},
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


@pytest.mark.parametrize("artifact", ["project.yaml", "mapping_workbook.csv", "profile_summary.json"])
def test_rejects_non_utf8_project_artifacts(project_root: Path, artifact: str) -> None:
    (project_root / "alpha" / artifact).write_bytes(b"\xff")

    with pytest.raises(ProjectValidationError):
        FilesystemProjectRepository(project_root).load("alpha")
