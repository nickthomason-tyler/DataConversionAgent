"""Proposal write-back command adapter."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from conversion_agent.mapping import writeback
from conversion_agent.mapping.apply import apply_typed
from conversion_agent.mapping.validation import load_validated_workbook, validate_proposal_document

from .common import render_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conversion-apply")
    parser.add_argument("input")
    parser.add_argument("proposals")
    parser.add_argument("output")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        return render_error(exc, debug=args.debug)


def _run(args: argparse.Namespace) -> int:
    model = load_validated_workbook(args.input)
    payload = json.loads(Path(args.proposals).read_text(encoding="utf-8"))
    application = apply_typed(model, validate_proposal_document(payload))
    write_report = writeback.write(model, args.output, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "validation": {
                    "accepted": len(application.accepted),
                    "no_good_match": len(application.no_match),
                    "rejected": [asdict(rejection) for rejection in application.rejected],
                },
                "written": asdict(write_report),
            },
            indent=2,
        )
    )
    return 0
