"""Process-wide cached access to packaged conversion resources."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

import yaml

from conversion_agent.projects.models import freeze_json

from .knowledge import KnowledgeIndex


def _root():
    return files("conversion_agent.resources").joinpath("data")


@lru_cache(maxsize=1)
def _dictionary():
    raw = yaml.safe_load(_root().joinpath("dct/dictionary.yaml").read_text(encoding="utf-8"))
    return freeze_json(raw)


@lru_cache(maxsize=1)
def _shared_knowledge() -> KnowledgeIndex:
    return KnowledgeIndex.from_traversable(_root().joinpath("knowledge"), scope="shared")


class ResourceCatalog:
    """Expose immutable, process-wide shared conversion resources."""

    def dictionary(self):
        return _dictionary()

    def shared_knowledge(self) -> KnowledgeIndex:
        return _shared_knowledge()
