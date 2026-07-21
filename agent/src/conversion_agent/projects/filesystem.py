"""Validated filesystem-backed project repository."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import stat
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
        project_dir = self.root / project_id
        project_file = project_dir / "project.yaml"
        mapping_file = project_dir / "mapping_workbook.csv"
        profile_file = project_dir / "profile_summary.json"
        root_fd = self._open_directory(self.root, "projects root")
        try:
            project_fd = self._open_project_directory(root_fd, project_id, project_dir)
            try:
                project_text = self._read_regular_text(project_fd, project_file, required=True)
                mapping_text = self._read_regular_text(project_fd, mapping_file, required=False)
                profile_text = self._read_regular_text(project_fd, profile_file, required=False)
            finally:
                os.close(project_fd)
        finally:
            os.close(root_fd)

        if project_text is None:  # required=True guarantees this; keep the type invariant explicit
            raise ProjectError(f"Missing project file: {project_file}")
        metadata = self._load_metadata(project_file, project_text)
        rows = self._load_mapping(mapping_file, mapping_text)
        profile = self._load_profile(profile_file, profile_text)
        return ProjectContext(
            project_id=project_id,
            root=project_dir,
            metadata=metadata,
            mapping_rows=rows,
            profile_summary=freeze_json(profile),
            knowledge_dir=self._resolve_knowledge_dir(project_dir),
        )

    @staticmethod
    def _open_directory(path: Path, label: str) -> int:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            return os.open(path, flags)
        except OSError as exc:
            raise ProjectError(f"Cannot open {label} {path}: {exc}") from exc

    @staticmethod
    def _open_project_directory(root_fd: int, project_id: str, path: Path) -> int:
        try:
            before = os.stat(project_id, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ProjectError(f"Missing project directory: {path}") from exc
        except OSError as exc:
            raise ProjectValidationError(f"Invalid project directory {path}: {exc}") from exc
        if stat.S_ISLNK(before.st_mode):
            raise ProjectValidationError(f"Project directory {path} must not be a symlink")
        if not stat.S_ISDIR(before.st_mode):
            raise ProjectValidationError(f"Project path must be a directory: {path}")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            project_fd = os.open(project_id, flags, dir_fd=root_fd)
        except OSError as exc:
            raise ProjectValidationError(f"Invalid project directory {path}: {exc}") from exc
        after = os.fstat(project_fd)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            os.close(project_fd)
            raise ProjectValidationError(f"Project directory changed while opening: {path}")
        return project_fd

    @staticmethod
    def _read_regular_text(project_fd: int, path: Path, *, required: bool) -> str | None:
        name = path.name
        try:
            before = os.stat(name, dir_fd=project_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            if required:
                raise ProjectError(f"Missing project file: {path}") from exc
            return None
        except OSError as exc:
            raise ProjectValidationError(f"Invalid project artifact {path}: {exc}") from exc
        if stat.S_ISLNK(before.st_mode):
            raise ProjectValidationError(f"Project artifact must not be a symlink: {path}")
        if not stat.S_ISREG(before.st_mode):
            raise ProjectValidationError(f"Project artifact must be a regular file: {path}")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            file_fd = os.open(name, flags, dir_fd=project_fd)
        except OSError as exc:
            raise ProjectValidationError(f"Invalid project artifact {path}: {exc}") from exc
        try:
            after = os.fstat(file_fd)
            if not stat.S_ISREG(after.st_mode) or (before.st_dev, before.st_ino) != (
                after.st_dev,
                after.st_ino,
            ):
                raise ProjectValidationError(f"Project artifact changed while opening: {path}")
            with os.fdopen(file_fd, "rb", closefd=False) as handle:
                data = handle.read()
        except OSError as exc:
            raise ProjectValidationError(f"Invalid project artifact {path}: {exc}") from exc
        finally:
            os.close(file_fd)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectValidationError(f"Project artifact is not UTF-8: {path}: {exc}") from exc

    @staticmethod
    def _load_metadata(path: Path, text: str) -> ProjectMetadata:
        try:
            raw = yaml.safe_load(text)
            doc = _ProjectDocument.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise ProjectValidationError(f"Invalid {path}: {exc}") from exc

        client_name = _required_text(doc.client_name, "client_name", path)
        source_system = _required_text(doc.source_system, "source_system", path)
        phase = _required_text(doc.phase, "phase", path)
        in_scope_entities = tuple(
            _required_text(entity, "in_scope_entities", path) for entity in doc.in_scope_entities
        )
        if len({entity.casefold() for entity in in_scope_entities}) != len(in_scope_entities):
            raise ProjectValidationError(
                f"Invalid {path}: in_scope_entities must contain unique values."
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
    def _load_mapping(path: Path, text: str | None) -> tuple[MappingRow, ...]:
        if text is None:
            return ()
        try:
            reader = csv.DictReader(io.StringIO(text, newline=""))
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
        except (csv.Error, KeyError, TypeError) as exc:
            raise ProjectValidationError(f"Invalid mapping workbook {path}: {exc}") from exc

    @staticmethod
    def _load_profile(path: Path, text: str | None) -> dict[str, Any]:
        if text is None:
            return {}
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProjectValidationError(f"Invalid profile summary {path}: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("entities", {}), dict):
            raise ProjectValidationError(
                f"Profile must be an object with object-valued entities: {path}"
            )
        for entity, details in value.get("entities", {}).items():
            if not isinstance(details, dict):
                raise ProjectValidationError(f"Invalid {path}: entities.{entity} must be an object")
        return value

    @staticmethod
    def _resolve_knowledge_dir(project_dir: Path) -> Path | None:
        knowledge_dir = project_dir / "knowledge"
        if not knowledge_dir.exists():
            return None
        try:
            resolved = knowledge_dir.resolve(strict=True)
        except OSError as exc:
            raise ProjectValidationError(
                f"Invalid knowledge directory {knowledge_dir}: {exc}"
            ) from exc
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
