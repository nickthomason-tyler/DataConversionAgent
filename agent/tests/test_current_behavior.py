from pathlib import Path

from conversion_agent.config import load_project
from conversion_agent.mapping.match import Matcher


def test_example_project_and_matcher_baseline() -> None:
    project = load_project("example-client")
    assert project.metadata.client_name == "City of Exampleton"
    assert project.metadata.source_system == "SQL Server (legacy permitting system)"
    assert project.metadata.in_scope_entities == ("permits", "contacts", "business_licenses")
    assert len(project.mapping_rows) == 10
    assert project.mapping_rows[0].source_column == "PERMIT_NO"
    assert project.mapping_rows[0].target_column == "permit_number"
    assert project.profile_summary["entities"]["permits"]["row_count"] == 184220
    assert project.mapping_status_counts == {
        "confirmed": 5,
        "blocked-on-config": 3,
        "draft": 2,
    }
    assert Matcher({"1c": "commercial"}).norm("1C-ELEC", 3) == "commercial electrical"


def test_project_root_fixture_creates_a_minimal_project(project_root: Path) -> None:
    project = project_root / "alpha"
    assert project.name == "alpha"
