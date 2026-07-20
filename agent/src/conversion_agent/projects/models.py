"""Immutable models for a loaded conversion project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ProjectMetadata:
    schema_version: int
    client_name: str
    source_system: str
    phase: str
    in_scope_entities: tuple[str, ...]
    conversion_lead: str | None
    client_data_steward: str | None
    extras: Mapping[str, Any]


@dataclass(frozen=True)
class MappingRow:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    rule: str
    status: str
    owner: str


@dataclass(frozen=True)
class ProjectContext:
    project_id: str
    root: Path
    metadata: ProjectMetadata
    mapping_rows: tuple[MappingRow, ...]
    profile_summary: Mapping[str, Any]
    knowledge_dir: Path | None

    @property
    def mapping_status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.mapping_rows:
            key = row.status.strip().lower() or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return counts


def freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    return value
