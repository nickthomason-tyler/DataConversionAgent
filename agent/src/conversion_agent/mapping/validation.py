"""Validation for mapping workbooks and externally supplied proposals."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from conversion_agent.core.errors import WorkbookError

from . import workbook


class ProposalInput(BaseModel):
    """One externally produced mapping recommendation."""

    model_config = ConfigDict(extra="forbid")

    tab: str = Field(min_length=1)
    section: str = Field(min_length=1)
    source: tuple[str, ...] = Field(min_length=1)
    dest: tuple[str, ...] | None
    confidence: float = Field(default=0.7, ge=0, le=1)
    rationale: str = ""


class ProposalDocument(BaseModel):
    """The complete external proposal payload."""

    model_config = ConfigDict(extra="forbid")

    proposals: tuple[ProposalInput, ...]


def validate_proposal_document(payload: object) -> ProposalDocument:
    """Parse a proposal payload and reject duplicate source recommendations."""
    try:
        document = ProposalDocument.model_validate(payload)
    except ValidationError as exc:
        raise WorkbookError(f"Invalid proposal document: {exc}") from exc

    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for proposal in document.proposals:
        key = (proposal.tab, proposal.section, proposal.source)
        if key in seen:
            raise WorkbookError(f"Duplicate proposal key: {key}")
        seen.add(key)
    return document


def load_validated_workbook(path: str | Path):
    """Load a crosswalk only after its structural mapping contract is verified."""
    try:
        model = workbook.load(str(path))
    except (
        BadZipFile,
        InvalidFileException,
        KeyError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise WorkbookError(f"Invalid workbook {path}: {exc}") from exc

    if not model.spec:
        raise WorkbookError(f"Workbook {path} has no valid LookupSpec contract")
    if not model.sections:
        raise WorkbookError(f"Workbook {path} has no mapping sections")

    for section in model.sections:
        if not section.src_cols or not section.dst_cols:
            raise WorkbookError(f"Section {section.key} has invalid source/destination arity")
        if len(section.dest_lists) < len(section.dst_cols):
            raise WorkbookError(f"Section {section.key} is missing destination pick lists")
        if len(section.dst_cols) == 2 and section.cascade:
            invalid = set(section.cascade) - set(section.dest_lists[0])
            if invalid:
                raise WorkbookError(
                    f"Section {section.key} has invalid cascade keys: {sorted(invalid)}"
                )
    return model
