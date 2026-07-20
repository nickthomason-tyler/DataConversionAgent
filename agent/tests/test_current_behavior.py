from pathlib import Path

from conversion_agent.config import load_project
from conversion_agent.mapping.match import Matcher


def test_example_project_and_matcher_baseline() -> None:
    project = load_project("example-client")
    assert project.mapping_status_counts == {
        "confirmed": 5,
        "blocked-on-config": 3,
        "draft": 2,
    }
    assert Matcher({"1c": "commercial"}).norm("1C-ELEC", 3) == "commercial electrical"


def test_project_root_fixture_creates_a_minimal_project(project_root: Path) -> None:
    project = project_root / "alpha"
    assert project.name == "alpha"
