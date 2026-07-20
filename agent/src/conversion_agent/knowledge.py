"""Compatibility surface for shared conversion-knowledge search."""

from __future__ import annotations

from .resources.catalog import ResourceCatalog
from .resources.knowledge import Chunk


def search(query: str, top_k: int = 5) -> list[Chunk]:
    """Search the packaged shared knowledge base using the legacy API."""
    return ResourceCatalog().shared_knowledge().search(query, top_k)
