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
    def name(self) -> str:
        """Legacy alias retained for the current CLI and tool surface."""
        return self.project_id

    @property
    def project(self) -> Mapping[str, Any]:
        """Legacy project-document view backed by immutable typed metadata."""
        return MappingProxyType(
            {
                "schema_version": self.metadata.schema_version,
                "client_name": self.metadata.client_name,
                "source_system": self.metadata.source_system,
                "phase": self.metadata.phase,
                "in_scope_entities": self.metadata.in_scope_entities,
                "conversion_lead": self.metadata.conversion_lead,
                "client_data_steward": self.metadata.client_data_steward,
                **self.metadata.extras,
            }
        )

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
