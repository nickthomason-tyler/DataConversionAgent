"""Typed orchestration for deterministic and model-assisted mapping runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import llm, match, writeback
from .validation import load_validated_workbook


@dataclass(frozen=True)
class MappingRequest:
    input_path: Path
    output_path: Path
    token_map: dict[str, str] = field(default_factory=dict)
    use_llm: bool = False
    project_id: str | None = None
    overwrite: bool = False


@dataclass(frozen=True)
class MappingReport:
    rows: int
    premapped: int
    deterministic: int
    model_proposed: int
    remaining: int
    warnings: tuple[str, ...] = ()


def build_report(model, written: object | None = None) -> MappingReport:
    """Summarize a completed in-memory mapping model before write verification."""
    rows = sum(len(section.rows) for section in model.sections)
    premapped = sum(
        sum(any(value.strip() for value in row.existing) for row in section.rows)
        for section in model.sections
    )
    model_proposed = sum(
        sum(proposal.method == "llm" for proposal in section.proposals.values())
        for section in model.sections
    )
    deterministic = sum(
        sum(proposal.method != "llm" for proposal in section.proposals.values())
        for section in model.sections
    )
    remaining = sum(len(section.unmatched) for section in model.sections)
    warnings = tuple(getattr(written, "warnings", ()))
    return MappingReport(rows, premapped, deterministic, model_proposed, remaining, warnings)


class MappingService:
    """Coordinate validated workbook parsing, matching, and output write-back."""

    def __init__(self, *, repository=None, backend_factory=None):
        self.repository = repository
        self.backend_factory = backend_factory

    def run(self, request: MappingRequest) -> MappingReport:
        model = load_validated_workbook(request.input_path)
        project = self.repository.load(request.project_id) if request.project_id else None

        for section in model.sections:
            match.run(section, token_map=request.token_map)

        if request.use_llm:
            if self.backend_factory is None:
                raise ValueError("A backend factory is required when use_llm is enabled")
            client = self.backend_factory.create()
            retries = self.backend_factory.settings.backend_retries
            source_system = project.metadata.source_system if project else None
            for section in model.sections:
                llm.run(
                    section,
                    client=client,
                    model_id=self.backend_factory.model_id,
                    source_system=source_system,
                    retries=retries,
                )

        written = writeback.write(model, str(request.output_path), overwrite=request.overwrite)
        return build_report(model, written)
