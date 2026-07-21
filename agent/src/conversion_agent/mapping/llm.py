"""Lane 2 — model-assisted matching with structured outputs.

For values Lane 1 could not claim, ask Claude to choose from the section's
actual pick list. The output schema constrains proposals to valid options
(plus an explicit no-good-match), so an unconfigured value can never be
proposed. Requires ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import anthropic

from .. import backend
from ..core.errors import WorkbookError
from ..guidance.backends import run_with_retries
from .model import Proposal, Section

BATCH = 40
MAX_BATCH = 40
MAX_CANDIDATES = 500
MIN_CONFIDENCE = 0.5  # below this we leave the row for a human


def build_system_prompt(source_system: str | None) -> str:
    """Build project-aware, source-neutral instructions for the model lane."""
    source = source_system.strip() if source_system and source_system.strip() else "a legacy system"
    return f"""You map legacy lookup values from {source} to configured EPL values.

Rules:
- Choose destination values ONLY from the provided candidate list.
- Expand abbreviations and reason about the source meaning without assuming a specific vendor.
- If no candidate is a faithful semantic match, use no_good_match.
- Report calibrated confidence: 0.9+ only when the meaning is unambiguous.
"""


def _schema(candidates: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["mappings"],
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["source", "match", "confidence", "rationale"],
                    "properties": {
                        "source": {"type": "string"},
                        "match": {
                            "anyOf": [
                                {"type": "string", "enum": candidates},
                                {"type": "null"},
                            ],
                            "description": "Chosen destination value, or null for no_good_match",
                        },
                        "confidence": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                },
            }
        },
    }


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, Mapping) else None
    return None


def _validate_batch_result(
    result: object,
    *,
    expected_sources: list[str],
    candidates: list[str],
    section_key: str,
) -> list[Mapping[str, Any]]:
    """Validate one complete backend response without mutating the section."""
    document = _as_mapping(result)
    if document is None or set(document) != {"mappings"}:
        raise WorkbookError(
            f"Invalid model proposal batch for {section_key}: expected a mappings object"
        )
    mappings = document["mappings"]
    if not isinstance(mappings, list) or len(mappings) != len(expected_sources):
        raise WorkbookError(
            f"Invalid model proposal batch for {section_key}: expected exactly "
            f"{len(expected_sources)} mappings"
        )

    validated: list[Mapping[str, Any]] = []
    sources: list[str] = []
    required = {"source", "match", "confidence", "rationale"}
    for index, item in enumerate(mappings):
        mapping = _as_mapping(item)
        if mapping is None or set(mapping) != required:
            raise WorkbookError(
                f"Invalid model proposal batch for {section_key}: mapping {index} has "
                "invalid fields"
            )
        source = mapping["source"]
        match = mapping["match"]
        confidence = mapping["confidence"]
        rationale = mapping["rationale"]
        if not isinstance(source, str):
            raise WorkbookError(
                f"Invalid model proposal batch for {section_key}: source must be text"
            )
        if match is not None and (not isinstance(match, str) or match not in candidates):
            raise WorkbookError(
                f"Invalid model proposal batch for {section_key}: destination {match!r} "
                "is not in the bounded candidate list"
            )
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            raise WorkbookError(
                f"Invalid model proposal batch for {section_key}: confidence must be in [0, 1]"
            )
        if not isinstance(rationale, str):
            raise WorkbookError(
                f"Invalid model proposal batch for {section_key}: rationale must be text"
            )
        sources.append(source)
        validated.append(mapping)

    if len(set(sources)) != len(sources) or set(sources) != set(expected_sources):
        raise WorkbookError(
            f"Invalid model proposal batch for {section_key}: response sources must be "
            "the exact unique pending sources"
        )
    return validated


def run(
    section: Section,
    client: anthropic.Anthropic | None = None,
    *,
    model_id: str | None = None,
    source_system: str | None = None,
    retries: int = 2,
) -> None:
    """Propose mappings for rows Lane 1 left unmatched (single-dest sections)."""
    if not section.dest_lists or len(section.dst_cols) != 1:
        return  # multi-column sections need the two-stage flow; see cli notes
    candidates = section.dest_lists[0]
    if len(candidates) > MAX_CANDIDATES:
        raise WorkbookError(
            f"Section {section.key} exceeds the model candidate limit of {MAX_CANDIDATES}"
        )
    if not candidates or any(not isinstance(candidate, str) for candidate in candidates):
        raise WorkbookError(f"Section {section.key} has an invalid model candidate list")
    if not 1 <= BATCH <= MAX_BATCH:
        raise WorkbookError(f"Configured model batch limit must be between 1 and {MAX_BATCH}")

    pending = list(section.unmatched)
    pending_sources = [" | ".join(value for value in row.values if value) for row in pending]
    if len(set(pending_sources)) != len(pending_sources):
        raise WorkbookError(f"Section {section.key} must have unique pending sources")
    if not pending:
        return

    client = client or backend.make_client()
    model_id = model_id or backend.model_id()
    staged: dict[int, Proposal] = {}
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        sources = pending_sources[start : start + BATCH]
        response = run_with_retries(
            lambda: client.messages.parse(
                model=model_id,
                max_tokens=16000,
                system=build_system_prompt(source_system),
                output_config={"format": {"type": "json_schema", "schema": _schema(candidates)}},
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Section: {section.key}\n"
                            f"Candidate destination values:\n"
                            + "\n".join(f"- {c}" for c in candidates)
                            + "\n\nMap each legacy value (return one entry per value, in order):\n"
                            + "\n".join(f"- {s}" for s in sources)
                        ),
                    }
                ],
            ),
            retries=retries,
        )
        mappings = _validate_batch_result(
            response.parsed_output,
            expected_sources=sources,
            candidates=candidates,
            section_key=section.key,
        )
        by_source = {mapping["source"]: mapping for mapping in mappings}
        for row, source in zip(batch, sources):
            m = by_source.get(source)
            if m is None or m["match"] is None or float(m["confidence"]) < MIN_CONFIDENCE:
                continue
            confidence = float(m["confidence"])
            staged[row.row_idx] = Proposal(
                dest=(m["match"],),
                method="llm",
                confidence=confidence,
                note=f"proposed ({confidence:.0%}): {m['rationale'][:160]}",
            )
    section.proposals.update(staged)
