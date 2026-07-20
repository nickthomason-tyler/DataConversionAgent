"""Lane 2 — model-assisted matching with structured outputs.

For values Lane 1 could not claim, ask Claude to choose from the section's
actual pick list. The output schema constrains proposals to valid options
(plus an explicit no-good-match), so an unconfigured value can never be
proposed. Requires ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""

from __future__ import annotations

import anthropic

from .. import backend
from .model import Proposal, Section

BATCH = 40
MIN_CONFIDENCE = 0.5   # below this we leave the row for a human

SYSTEM = """\
You map legacy lookup values from a municipality's New World Permitting
system to the configured values of their new EPL (Energov) system.

Rules:
- Choose destination values ONLY from the provided candidate list.
- Legacy values often carry sort-order prefixes (1-, 1C-, 2R-) and
  abbreviations (COM=commercial, RES=residential, PP=private provider,
  BLDG=building, ELEC=electrical...). Expand and reason about the meaning.
- If no candidate is a faithful semantic match, use no_good_match — never
  force a mapping. A retired or unconfigured legacy value is a finding.
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


def run(section: Section, client: anthropic.Anthropic | None = None) -> None:
    """Propose mappings for rows Lane 1 left unmatched (single-dest sections)."""
    if not section.dest_lists or len(section.dst_cols) != 1:
        return  # multi-column sections need the two-stage flow; see cli notes
    client = client or backend.make_client()
    candidates = section.dest_lists[0]
    pending = section.unmatched
    for start in range(0, len(pending), BATCH):
        batch = pending[start:start + BATCH]
        sources = [" | ".join(v for v in r.values if v) for r in batch]
        response = client.messages.parse(
            model=backend.model_id(),
            max_tokens=16000,
            system=SYSTEM,
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
