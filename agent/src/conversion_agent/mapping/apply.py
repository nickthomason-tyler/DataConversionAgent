"""Apply externally produced mapping proposals through the validation gate.

Proposals can come from any judgment source — the Lane 2 API caller, an
interactive Claude session, or a consultant's bulk edit. Every proposal is
validated the same way before touching the workbook: destination values must
be byte-exact members of the section's pick lists, two-column pairs must
satisfy the cascade constraint, and human-entered cells are never overwritten.
Invalid proposals are rejected and reported, never silently dropped.

Proposal file format (JSON):
{
  "proposals": [
    {"tab": "Permits", "section": "Permit Type Class",
     "source": ["1C-ADD", "1COM-ADDITION"],
     "dest": ["Commercial Building", "Addition"],
     "confidence": 0.9, "rationale": "..."},
    {"tab": "Permits", "section": "Permit Type Class",
     "source": ["1-BC SOUND PROG", "1-SOUND INSULATION PROGRAM"],
     "dest": null, "rationale": "no configured equivalent"}   # no_good_match
  ]
}

Usage:
    python -m conversion_agent.mapping.apply <workbook.xlsx> <proposals.json> <output.xlsx>
"""

from __future__ import annotations

import json
import sys

from . import workbook, writeback
from .model import Proposal


def apply(model, proposals: list[dict]) -> dict:
    accepted, rejected, no_match = 0, [], 0
    by_key: dict[tuple[str, str], dict[tuple, dict]] = {}
    for p in proposals:
        by_key.setdefault((p["tab"], p["section"]), {})[tuple(p["source"])] = p

    for sec in model.sections:
        pending = by_key.get((sec.tab, sec.title), {})
        if not pending:
            continue
        for row in sec.rows:
            p = pending.get(row.values)
            if p is None:
                continue
            if any(v.strip() for v in row.existing) or row.row_idx in sec.proposals:
                rejected.append((p, "already mapped"))
                continue
            if p.get("dest") is None:
                no_match += 1
                sec.proposals[row.row_idx] = Proposal(
                    dest=tuple("" for _ in sec.dst_cols), method="llm",
                    confidence=float(p.get("confidence", 0.0)),
                    note=f"NO GOOD MATCH — {p.get('rationale', '')[:180]}")
                continue
            dest = tuple(p["dest"])
            if len(dest) != len(sec.dst_cols):
                rejected.append((p, "wrong destination arity"))
                continue
            ok = all(d in lst for d, lst in zip(dest, sec.dest_lists)) if sec.dest_lists else False
            if not ok:
                rejected.append((p, "value not in pick list"))
                continue
            if len(dest) == 2 and sec.cascade and dest[1] not in sec.cascade.get(dest[0], []):
                rejected.append((p, f"cascade violation: '{dest[1]}' not valid for '{dest[0]}'"))
                continue
            sec.proposals[row.row_idx] = Proposal(
                dest=dest, method="llm", confidence=float(p.get("confidence", 0.7)),
                note=f"proposed ({p.get('confidence', 0.7):.0%}): {p.get('rationale', '')[:180]}")
            accepted += 1
    return {"accepted": accepted, "no_good_match": no_match,
            "rejected": [(p["source"], reason) for p, reason in rejected]}


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(1)
    in_path, proposals_path, out_path = sys.argv[1:4]
    model = workbook.load(in_path)
    payload = json.load(open(proposals_path))
    result = apply(model, payload["proposals"])
    written = writeback.write(model, out_path)
    print(json.dumps({"validation": {**result, "rejected": result["rejected"]},
                      "written": written}, indent=2, default=str))


if __name__ == "__main__":
    main()
