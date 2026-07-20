"""Validated filesystem-backed project repository."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from conversion_agent.core.errors import ProjectError, ProjectValidationError

from .models import MappingRow, ProjectContext, ProjectMetadata, freeze_json

PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
MAPPING_FIELDS = tuple(MappingRow.__dataclass_fields__)


class _ProjectDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = Field(default=1, ge=1)
    client_name: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    in_scope_entities: list[str] = Field(min_length=1)
    conversion_lead: str | None = None
    client_data_steward: str | None = None


class FilesystemProjectRepository:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()

    def load(self, project_id: str) -> ProjectContext:
        if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
            raise ProjectValidationError(f"Unsafe project identifier: {project_id!r}")
        project_dir = (self.root / project_id).resolve()
        if project_dir.parent != self.root:
            raise ProjectValidationError("Project path escapes the configured projects root.")

        project_file = project_dir / "project.yaml"
        if not project_file.is_file():
            raise ProjectError(f"Missing project file: {project_file}")
        metadata = self._load_metadata(project_file)
        rows = self._load_mapping(project_dir / "mapping_workbook.csv")
        profile = self._load_profile(project_dir / "profile_summary.json")
        return ProjectContext(
            project_id=project_id,
            root=project_dir,
            metadata=metadata,
            mapping_rows=rows,
            profile_summary=freeze_json(profile),
            knowledge_dir=self._resolve_knowledge_dir(project_dir),
        )

    @staticmethod
    def _load_metadata(path: Path) -> ProjectMetadata:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            doc = _ProjectDocument.model_validate(raw)
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
            raise ProjectValidationError(f"Invalid {path}: {exc}") from exc

        client_name = _required_text(doc.client_name, "client_name", path)
        source_system = _required_text(doc.source_system, "source_system", path)
        phase = _required_text(doc.phase, "phase", path)
        in_scope_entities = tuple(
            dict.fromkeys(
                _required_text(entity, "in_scope_entities", path)
                for entity in doc.in_scope_entities
            )
        )
        return ProjectMetadata(
            schema_version=doc.schema_version,
            client_name=client_name,
            source_system=source_system,
            phase=phase,
            in_scope_entities=in_scope_entities,
            conversion_lead=doc.conversion_lead,
            client_data_steward=doc.client_data_steward,
            extras=freeze_json(doc.model_extra or {}),
        )

    @staticmethod
    def _load_mapping(path: Path) -> tuple[MappingRow, ...]:
        if not path.exists():
            return ()
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != MAPPING_FIELDS:
                    raise ProjectValidationError(f"Invalid mapping headers in {path}")
                rows: list[MappingRow] = []
                for line_number, row in enumerate(reader, start=2):
                    if None in row:
                        raise ProjectValidationError(
                            f"Invalid mapping row {line_number} in {path}: too many values"
                        )
                    values: dict[str, str] = {}
                    for name in MAPPING_FIELDS:
                        value = row.get(name)
                        if not isinstance(value, str) or not value.strip():
                            raise ProjectValidationError(
                                f"Invalid mapping row {line_number} in {path}: {name} is required"
                            )
                        values[name] = value
                    rows.append(MappingRow(**values))
                return tuple(rows)
        except (OSError, UnicodeDecodeError, csv.Error, KeyError, TypeError) as exc:
            raise ProjectValidationError(f"Invalid mapping workbook {path}: {exc}") from exc

    @staticmethod
    def _load_profile(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectValidationError(f"Invalid profile summary {path}: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("entities", {}), dict):
            raise ProjectValidationError(
                f"Profile must be an object with object-valued entities: {path}"
            )
        return value

    @staticmethod
    def _resolve_knowledge_dir(project_dir: Path) -> Path | None:
        knowledge_dir = project_dir / "knowledge"
        if not knowledge_dir.exists():
            return None
        try:
            resolved = knowledge_dir.resolve(strict=True)
        except OSError as exc:
            raise ProjectValidationError(f"Invalid knowledge directory {knowledge_dir}: {exc}") from exc
        try:
            resolved.relative_to(project_dir)
        except ValueError as exc:
            raise ProjectValidationError(
                f"Knowledge directory escapes project directory: {knowledge_dir}"
            ) from exc
        if not resolved.is_dir():
            return None
        return resolved


def _required_text(value: str, field: str, path: Path) -> str:
    normalized = value.strip()
    if not normalized:
        raise ProjectValidationError(f"Invalid {path}: {field} cannot be blank")
    return normalized
