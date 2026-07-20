"""Interactive chat CLI: python -m conversion_agent.cli <client-name>"""

from __future__ import annotations

import sys

from .agent import ConversionAgent
from .config import load_project


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m conversion_agent.cli <client-name>")
        raise SystemExit(1)

    project = load_project(sys.argv[1])
    agent = ConversionAgent(project)
    print(f"Conversion Guidance Agent — client: {project.name} (Ctrl-D to exit)")

    while True:
        try:
            question = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        print("\nagent> " + agent.ask(question))


if __name__ == "__main__":
    main()
