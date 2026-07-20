"""Run the golden question set through the agent and write answers for SME review.

Usage: python evals/run_evals.py [client-name]
Writes evals/results.md — grade it weekly; ship Phase 1 when consistently acceptable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conversion_agent.agent import ConversionAgent  # noqa: E402
from conversion_agent.config import load_project  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent


def main() -> None:
    client = sys.argv[1] if len(sys.argv) > 1 else "example-client"
    spec = yaml.safe_load((EVALS_DIR / "golden_questions.yaml").read_text())

    lines = [f"# Eval results — client: {client}\n"]
    for q in spec["questions"]:
        # Fresh agent per question: evals grade single-turn answers.
        agent = ConversionAgent(load_project(client))
        print(f"[{q['id']}] {q['question']}")
        answer = agent.ask(q["question"])
        lines += [
            f"## {q['id']}: {q['question']}\n",
            "**Must contain:**",
            *[f"- {c}" for c in q["must_contain"]],
            "\n**Answer:**\n",
            answer,
            "\n**SME grade (pass/fail + notes):** _____\n",
            "---\n",
        ]

    out = EVALS_DIR / "results.md"
    out.write_text("\n".join(lines))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
