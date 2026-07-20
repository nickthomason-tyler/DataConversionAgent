"""Run the mapping pipeline over a crosswalk workbook.

Usage:
    python -m conversion_agent.mapping.cli <workbook.xlsx> <output.xlsx> \
        [--rules client_rules.yaml] [--llm]

Lane 1 (deterministic) always runs; --rules supplies the per-client token
rule pack (see rules/README). --llm adds Lane 2 (Claude proposals,
single-destination sections) for whatever Lane 1 left unmatched; it requires
ANTHROPIC_API_KEY or an `ant auth login` profile.
"""

from __future__ import annotations

import sys

import yaml

from . import match, workbook, writeback


def main() -> None:
    argv = sys.argv[1:]
    use_llm = "--llm" in argv
    token_map: dict[str, str] = {}
    if "--rules" in argv:
        rules_path = argv[argv.index("--rules") + 1]
        rules = yaml.safe_load(open(rules_path)) or {}
        token_map = rules.get("token_map", {})
        argv.remove("--rules")
        argv.remove(rules_path)
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        raise SystemExit(1)
    in_path, out_path = args

    model = workbook.load(in_path)
    print(f"Parsed {len(model.sections)} sections from {in_path}"
          + (f" (rule pack: {len(token_map)} tokens)" if token_map else ""))

    for sec in model.sections:
        match.run(sec, token_map=token_map)

    if use_llm:
        from . import llm
        for sec in model.sections:
            if sec.unmatched and len(sec.dst_cols) == 1:
                llm.run(sec)

    print(f"\n{'section':52} {'rows':>6} {'pre':>5} {'auto':>5} {'llm':>5} {'left':>6}")
    totals = dict.fromkeys(("rows", "premapped", "auto", "llm", "remaining"), 0)
    for sec in model.sections:
        s = match.stats(sec)
        n_llm = sum(1 for p in sec.proposals.values() if p.method == "llm")
        s["auto"] -= n_llm
        s["llm"] = n_llm
        s["remaining"] -= 0
        for k in totals:
            totals[k] += s.get(k, 0)
        print(f"{s['section']:52} {s['rows']:>6} {s['premapped']:>5} {s['auto']:>5} {n_llm:>5} {s['remaining'] - n_llm:>6}")
    print(f"{'TOTAL':52} {totals['rows']:>6} {totals['premapped']:>5} {totals['auto']:>5} {totals['llm']:>5} {totals['remaining'] - totals['llm']:>6}")

    written = writeback.write(model, out_path)
    print(f"\nWrote {out_path}: {written['auto']} deterministic, {written['llm']} model-proposed")


if __name__ == "__main__":
    main()
