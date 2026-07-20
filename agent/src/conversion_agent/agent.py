"""Backward-compatible project-scoped guidance agent."""

from __future__ import annotations

import os

from .core.settings import AppSettings
from .guidance.backends import AnthropicBackendFactory
from .guidance.session import GuidanceSession, build_system
from .guidance.tools import build_tools
from .projects.models import ProjectContext
from .resources.catalog import ResourceCatalog
from .resources.knowledge import KnowledgeIndex


class ConversionAgent(GuidanceSession):
    """Backward-compatible project-scoped session constructor."""

    def __init__(self, project: ProjectContext, settings: AppSettings | None = None):
        settings = settings or AppSettings.from_sources(
            projects_root=project.root.parent,
            environ=os.environ,
            development_root=None,
        )
        catalog = ResourceCatalog()
        factory = AnthropicBackendFactory(settings)
        index = KnowledgeIndex.for_project(catalog.shared_knowledge(), project)
        super().__init__(
            project=project,
            client=factory.create(),
            model_id=factory.model_id,
            tools=build_tools(project, index, catalog.dictionary(), settings),
            settings=settings,
            system=build_system(project),
        )


__all__ = ["ConversionAgent", "build_system"]
