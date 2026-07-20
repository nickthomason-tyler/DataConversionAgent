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
