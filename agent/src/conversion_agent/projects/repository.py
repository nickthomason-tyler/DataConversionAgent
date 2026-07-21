"""Project repository protocol."""

from typing import Protocol

from .models import ProjectContext


class ProjectRepository(Protocol):
    def load(self, project_id: str) -> ProjectContext: ...
