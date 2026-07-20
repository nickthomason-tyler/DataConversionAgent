"""Keyword retrieval over the markdown knowledge base.

Deliberately simple for Phase 1: score each document section by term overlap
and return the best chunks with file citations. The tool contract
(query in, cited chunks out) is stable, so this can be swapped for an
embeddings index later without touching the agent or its prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import KNOWLEDGE_DIR

_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class Chunk:
    source: str  # relative path, e.g. "playbook/02-initial-etl-migration.md"
    heading: str
    text: str
    score: float


def _tokenize(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _split_sections(path: Path) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = path.stem
    lines: list[str] = []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            if lines:
                sections.append((heading, "\n".join(lines).strip()))
            heading = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)
    if lines:
        sections.append((heading, "\n".join(lines).strip()))
    return [(h, t) for h, t in sections if t]


def search(query: str, top_k: int = 5) -> list[Chunk]:
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    results: list[Chunk] = []
    for path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        rel = str(path.relative_to(KNOWLEDGE_DIR))
        for heading, text in _split_sections(path):
            section_terms = _tokenize(heading + " " + text)
            overlap = query_terms & section_terms
            if not overlap:
                continue
            # weight rarer matches implicitly by normalizing on section size
            score = len(overlap) / len(query_terms) + 0.1 * len(overlap) / max(
                len(section_terms), 1
            )
            results.append(Chunk(source=rel, heading=heading, text=text, score=score))

    results.sort(key=lambda c: c.score, reverse=True)
    return results[:top_k]
