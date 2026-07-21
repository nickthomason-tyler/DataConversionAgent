"""Run golden questions through project-bound guidance sessions for SME review.

Usage: python evals/run_evals.py [client-name] [--projects-root PATH]
Writes evals/results.md. Live model credentials are required because this is a
human-review evaluation, not part of the default offline test suite.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversion_agent.core.settings import AppSettings  # noqa: E402
from conversion_agent.guidance.backends import AnthropicBackendFactory  # noqa: E402
from conversion_agent.guidance.service import GuidanceService  # noqa: E402
from conversion_agent.projects.filesystem import FilesystemProjectRepository  # noqa: E402
from conversion_agent.resources.catalog import ResourceCatalog  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", nargs="?", default="example-client")
    parser.add_argument("--projects-root")
    return parser


def build_service(args: argparse.Namespace) -> GuidanceService:
    """Construct the same project-aware service used by the public CLI."""
    settings = AppSettings.from_sources(
        projects_root=args.projects_root,
        environ=os.environ,
        development_root=Path(__file__).resolve().parents[1] / "clients",
    )
    if settings.projects_root is None:
        raise RuntimeError("A projects root is required for evaluations.")
    return GuidanceService(
        settings,
        FilesystemProjectRepository(settings.projects_root),
        ResourceCatalog(),
        AnthropicBackendFactory(settings),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    spec = yaml.safe_load((EVALS_DIR / "golden_questions.yaml").read_text(encoding="utf-8"))
    service = build_service(args)

    lines = [f"# Eval results — client: {args.client}\n"]
    for question in spec["questions"]:
        # A fresh session keeps every eval question a single-turn assessment.
        session = service.open_session(args.client)
        print(f"[{question['id']}] {question['question']}")
        answer = session.ask(question["question"])
        lines += [
            f"## {question['id']}: {question['question']}\n",
            "**Must contain:**",
            *[f"- {criterion}" for criterion in question["must_contain"]],
            "\n**Answer:**\n",
            answer,
            "\n**SME grade (pass/fail + notes):** _____\n",
            "---\n",
        ]

    out = EVALS_DIR / "results.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
