"""Factory for opening project-isolated guidance sessions."""

from __future__ import annotations

from conversion_agent.resources.knowledge import KnowledgeIndex

from .session import GuidanceSession, build_system
from .tools import build_tools


class GuidanceService:
    def __init__(self, settings, repository, catalog, backend_factory):
        self.settings = settings
        self.repository = repository
        self.catalog = catalog
        self.backend_factory = backend_factory

    def open_session(self, project_id: str) -> GuidanceSession:
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
