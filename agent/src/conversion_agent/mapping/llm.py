"""Lane 2 — model-assisted matching with structured outputs.

For values Lane 1 could not claim, ask Claude to choose from the section's
actual pick list. The output schema constrains proposals to valid options
(plus an explicit no-good-match), so an unconfigured value can never be
proposed. Requires ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""

from __future__ import annotations

import anthropic

from .. import backend
from ..guidance.backends import run_with_retries
from .model import Proposal, Section

BATCH = 40
MIN_CONFIDENCE = 0.5   # below this we leave the row for a human

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
    client = client or backend.make_client()
    model_id = model_id or backend.model_id()
    candidates = section.dest_lists[0]
    pending = section.unmatched
    for start in range(0, len(pending), BATCH):
        batch = pending[start:start + BATCH]
        sources = [" | ".join(v for v in r.values if v) for r in batch]
        response = run_with_retries(
            lambda: client.messages.parse(
                model=model_id,
                max_tokens=16000,
                system=build_system_prompt(source_system),
                output_config={"format": {"type": "json_schema", "schema": _schema(candidates)}},
                messages=[{
                    "role": "user",
                    "content": (
                        f"Section: {section.key}\n"
                        f"Candidate destination values:\n"
                        + "\n".join(f"- {c}" for c in candidates)
                        + "\n\nMap each legacy value (return one entry per value, in order):\n"
                        + "\n".join(f"- {s}" for s in sources)
                    ),
                }],
            ),
            retries=retries,
        )
        result = response.parsed_output
        if result is None:
            continue
        by_source = {m["source"]: m for m in result["mappings"]}
        for row, source in zip(batch, sources):
            m = by_source.get(source)
            if not m or m["match"] is None or m["confidence"] < MIN_CONFIDENCE:
                continue
            section.proposals[row.row_idx] = Proposal(
                dest=(m["match"],), method="llm",
                confidence=float(m["confidence"]),
                note=f"proposed ({m['confidence']:.0%}): {m['rationale'][:160]}")
