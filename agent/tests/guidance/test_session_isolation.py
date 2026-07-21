from concurrent.futures import ThreadPoolExecutor

from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.service import GuidanceService
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog


class FakeBackendFactory:
    model_id = "fake-model"

    def create(self) -> object:
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
        alpha_json, beta_json = list(
            pool.map(
                lambda session: session.call_tool("get_mapping_status", {}),
                (alpha, beta),
            )
        )

    assert "Alpha City" in alpha_json and "Beta City" not in alpha_json
    assert "Beta City" in beta_json and "Alpha City" not in beta_json


def test_legacy_tools_module_has_no_active_project_state() -> None:
    import conversion_agent.tools as tools

    assert not hasattr(tools, "_project")
    assert not hasattr(tools, "set_project")
    assert not hasattr(tools, "_require_project")
