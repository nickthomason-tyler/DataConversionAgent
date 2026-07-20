"""Scoped keyword retrieval over packaged and project markdown knowledge."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Chunk:
    source: str
    heading: str
    text: str
    scope: str
    project_id: str | None = None
    score: float = 0.0

    @property
    def citation(self) -> str:
        if self.scope == "project":
            return f"[project source: {self.project_id}/{self.source} § {self.heading}]"
        return f"[source: {self.source} § {self.heading}]"


class KnowledgeIndex:
    def __init__(self, chunks: Iterable[Chunk]):
        self.chunks = tuple(chunks)

    @classmethod
    def for_project(cls, shared: "KnowledgeIndex", project) -> "KnowledgeIndex":
        chunks = list(shared.chunks)
        if project.knowledge_dir:
            chunks.extend(
                cls.from_path(project.knowledge_dir, project.root, project.project_id).chunks
            )
        return cls(chunks)

    @classmethod
    def from_traversable(cls, root, scope: str = "shared") -> "KnowledgeIndex":
        chunks: list[Chunk] = []
        for item, relative in _walk_traversable(root):
            if item.is_file() and relative.endswith(".md"):
                chunks.extend(_chunks(relative, item.read_text(encoding="utf-8"), scope))
        return cls(chunks)

    @classmethod
    def from_path(
        cls, knowledge_dir: Path, project_root: Path, project_id: str
    ) -> "KnowledgeIndex":
        project_root = project_root.resolve()
        chunks: list[Chunk] = []
        for path in sorted(knowledge_dir.rglob("*.md")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if project_root not in resolved.parents:
                raise ValueError(f"Project knowledge path escapes project root: {path}")
            source = resolved.relative_to(project_root).as_posix()
            chunks.extend(
                _chunks(
                    source,
                    resolved.read_text(encoding="utf-8"),
                    "project",
                    project_id,
                )
            )
        return cls(chunks)

    def search(self, query: str, top_k: int = 5) -> list[Chunk]:
        terms = set(_WORD.findall(query.lower()))
        scored = []
        for chunk in self.chunks:
            section_terms = set(_WORD.findall(f"{chunk.heading} {chunk.text}".lower()))
            overlap = terms & section_terms
            if overlap:
                scored.append(Chunk(**{**chunk.__dict__, "score": len(overlap) / len(terms)}))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]


def _walk_traversable(root, prefix: str = ""):
    for item in sorted(root.iterdir(), key=lambda candidate: candidate.name):
        relative = f"{prefix}/{item.name}" if prefix else item.name
        if item.is_dir():
            yield from _walk_traversable(item, relative)
        else:
            yield item, relative


def _chunks(source: str, text: str, scope: str, project_id: str | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading = Path(source).stem
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            body = "\n".join(lines).strip()
            if body:
                chunks.append(Chunk(source, heading, body, scope, project_id))
            heading = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)
    body = "\n".join(lines).strip()
    if body:
        chunks.append(Chunk(source, heading, body, scope, project_id))
    return chunks
