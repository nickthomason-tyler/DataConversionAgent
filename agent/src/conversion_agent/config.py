"""Compatibility helpers for loading projects and the shared DCT dictionary."""

from __future__ import annotations

from pathlib import Path

from .core.settings import AppSettings
from .projects.filesystem import FilesystemProjectRepository
from .projects.models import ProjectContext
from .resources.catalog import ResourceCatalog

AGENT_ROOT = Path(__file__).resolve().parents[2]
CLIENTS_DIR = AGENT_ROOT / "clients"

def load_project(
    client_name: str, projects_root: Path | str | None = None
) -> ProjectContext:
    """Load a project using the legacy client-name entry point.

    An explicit root takes precedence over the environment, while the bundled
    clients directory remains the development fallback for existing callers.
    """
    settings = AppSettings.from_sources(
        projects_root=projects_root,
        environ=__import__("os").environ,
        development_root=CLIENTS_DIR if CLIENTS_DIR.is_dir() else None,
    )
    if settings.projects_root is None:
        raise RuntimeError("A projects root is required to load a project")
    return FilesystemProjectRepository(settings.projects_root).load(client_name)


def load_dictionary():
    """Load the immutable packaged dictionary through the legacy API."""
    return ResourceCatalog().dictionary()
