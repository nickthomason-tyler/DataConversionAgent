"""Compatibility entry point for ``python -m conversion_agent.mapping.cli``."""

from conversion_agent.cli.mapping import main


if __name__ == "__main__":
    raise SystemExit(main())
