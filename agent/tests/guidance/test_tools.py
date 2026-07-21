import csv
import json
from pathlib import Path

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
    payload = json.loads(bound_tool_set.call("get_mapping_status", {"limit": 1, "offset": 0}))

    assert payload["result"]["returned"] == 1
    assert payload["result"]["truncated"] is True


def _build_tool_set(project_root: Path, settings: AppSettings):
    project = FilesystemProjectRepository(project_root).load("alpha")
    catalog = ResourceCatalog()
    return build_tools(
        project,
        KnowledgeIndex.for_project(catalog.shared_knowledge(), project),
        catalog.dictionary(),
        settings,
    )


def test_mapping_tool_uses_configured_default_limit_when_omitted(project_root: Path) -> None:
    mapping_file = project_root / "alpha" / "mapping_workbook.csv"
    with mapping_file.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["PERMITS", "ADDRESS", "permit", "address", "copy", "draft", "analyst"])
    tools = _build_tool_set(
        project_root,
        AppSettings(projects_root=project_root, mapping_default_limit=1),
    )

    payload = json.loads(tools.call("get_mapping_status", {}))

    assert payload["result"]["returned"] == 1
    assert payload["truncation"]["rows"] is True
    assert payload["truncation"]["characters"] is False


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("get_mapping_status", {}),
        ("lookup_dct_field", {"table": "permit"}),
        ("get_profile_summary", {}),
    ],
)
def test_json_tools_remain_valid_and_report_character_truncation_at_tight_limits(
    project_root: Path, tool_name: str, arguments: dict
) -> None:
    profile = project_root / "alpha" / "profile_summary.json"
    profile.write_text(
        json.dumps({"entities": {"permits": {"notes": "x" * 2_000}}}),
        encoding="utf-8",
    )
    settings = AppSettings(
        projects_root=project_root,
        max_tool_chars=220,
        mapping_default_limit=1,
    )
    tools = _build_tool_set(project_root, settings)

    raw = tools.call(tool_name, arguments)
    result = json.loads(raw)

    assert len(raw) <= settings.max_tool_chars
    assert set(result) == {"result", "truncation"}
    assert result["truncation"]["characters"] is True
    assert result["truncation"]["character_limit"] == settings.max_tool_chars


@pytest.mark.parametrize(
    "arguments",
    [
        {"table": "unknown-" + "x" * 1_000},
        {"table": "permit", "column": "unknown-" + "x" * 1_000},
    ],
    ids=["long-unknown-table", "long-unknown-column"],
)
def test_unknown_dct_results_are_bounded_valid_json(
    project_root: Path, arguments: dict[str, str]
) -> None:
    settings = AppSettings(projects_root=project_root, max_tool_chars=220)
    tools = _build_tool_set(project_root, settings)

    raw = tools.call("lookup_dct_field", arguments)
    payload = json.loads(raw)

    assert len(raw) <= settings.max_tool_chars
    assert set(payload) == {"result", "truncation"}
    assert payload["truncation"]["characters"] is True
    assert isinstance(payload["result"], str)
    assert "[TRUNCATED]" in payload["result"]


def test_absent_profile_result_is_bounded_valid_json(project_root: Path) -> None:
    (project_root / "alpha" / "profile_summary.json").unlink()
    settings = AppSettings(projects_root=project_root, max_tool_chars=220)
    tools = _build_tool_set(project_root, settings)

    raw = tools.call("get_profile_summary", {})
    payload = json.loads(raw)

    assert len(raw) <= settings.max_tool_chars
    assert payload["result"] == "No profiling summary loaded for this client yet."
    assert payload["truncation"]["characters"] is False


def test_unknown_profile_entity_with_large_known_list_is_bounded_json(
    project_root: Path,
) -> None:
    profile = project_root / "alpha" / "profile_summary.json"
    profile.write_text(
        json.dumps(
            {
                "entities": {
                    f"entity-{index:03d}-{'x' * 30}": {"row_count": index} for index in range(100)
                }
            }
        ),
        encoding="utf-8",
    )
    settings = AppSettings(projects_root=project_root, max_tool_chars=220)
    tools = _build_tool_set(project_root, settings)

    raw = tools.call("get_profile_summary", {"entity": "missing"})
    payload = json.loads(raw)

    assert len(raw) <= settings.max_tool_chars
    assert payload["result"].startswith("No profile for entity 'missing'. Known:")
    assert "[TRUNCATED]" in payload["result"]
    assert payload["truncation"]["characters"] is True


def test_profile_truncation_key_cannot_collide_with_envelope_metadata(
    project_root: Path,
) -> None:
    profile = project_root / "alpha" / "profile_summary.json"
    profile.write_text(
        json.dumps(
            {
                "truncation": {"project_owned": True},
                "entities": {"permits": {"row_count": 10}},
            }
        ),
        encoding="utf-8",
    )
    tools = _build_tool_set(project_root, AppSettings(projects_root=project_root))

    payload = json.loads(tools.call("get_profile_summary", {}))

    assert payload["result"]["truncation"] == {"project_owned": True}
    assert payload["truncation"] == {
        "rows": False,
        "characters": False,
        "character_limit": 50_000,
    }


def test_knowledge_truncation_keeps_a_complete_citation_and_unambiguous_marker(
    project_root: Path,
) -> None:
    settings = AppSettings(projects_root=project_root, max_tool_chars=220)
    tools = _build_tool_set(project_root, settings)

    result = tools.call("search_knowledge_base", {"query": "conversion data project"})

    first_line = result.splitlines()[0]
    assert first_line.startswith("[source: ")
    assert first_line.endswith("]")
    assert result.endswith("[TRUNCATED: tool output exceeded 220 characters]")
    assert len(result) <= settings.max_tool_chars
