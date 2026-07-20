import csv
import json

import pytest

from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.tools import build_tools
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog
from conversion_agent.resources.knowledge import KnowledgeIndex


@pytest.fixture
def bound_tool_set(project_root):
    mapping_file = project_root / "alpha" / "mapping_workbook.csv"
    with mapping_file.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_table",
                "source_column",
                "target_table",
                "target_column",
                "rule",
                "status",
                "owner",
            ],
        )
        writer.writerow(
            {
                "source_table": "PERMITS",
                "source_column": "ADDRESS",
                "target_table": "permit",
                "target_column": "address",
                "rule": "copy",
                "status": "confirmed",
                "owner": "analyst",
            }
        )
    project = FilesystemProjectRepository(project_root).load("alpha")
    catalog = ResourceCatalog()
    return build_tools(
        project,
        KnowledgeIndex.for_project(catalog.shared_knowledge(), project),
        catalog.dictionary(),
        AppSettings(projects_root=project_root),
    )


def test_mapping_tool_is_bounded(bound_tool_set) -> None:
    result = json.loads(bound_tool_set.call("get_mapping_status", {"limit": 1, "offset": 0}))

    assert result["returned"] == 1
    assert result["truncated"] is True
