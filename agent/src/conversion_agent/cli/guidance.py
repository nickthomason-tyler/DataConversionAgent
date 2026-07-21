"""Interactive guidance command adapter."""

from __future__ import annotations

import argparse
import os
from typing import Sequence

from conversion_agent.config import CLIENTS_DIR
from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.backends import AnthropicBackendFactory
from conversion_agent.guidance.service import GuidanceService
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog

from .common import render_error


def build_parser() -> argparse.ArgumentParser:
    """Build the public parser without reading configuration or creating a backend."""
    parser = argparse.ArgumentParser(prog="conversion-agent")
    parser.add_argument("project")
    parser.add_argument("--projects-root")
    parser.add_argument("--backend", choices=("anthropic", "bedrock"))
    parser.add_argument("--model")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except Exception as exc:
        return render_error(exc, debug=args.debug)


def _run(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    if args.backend:
        env["CONVERSION_AGENT_BACKEND"] = args.backend
    if args.model:
        env["CONVERSION_AGENT_MODEL"] = args.model
    settings = AppSettings.from_sources(
        projects_root=args.projects_root,
        environ=env,
        development_root=CLIENTS_DIR if CLIENTS_DIR.is_dir() else None,
    )
    if settings.projects_root is None:
        raise RuntimeError("A projects root is required for guidance.")
    service = GuidanceService(
        settings,
        FilesystemProjectRepository(settings.projects_root),
        ResourceCatalog(),
        AnthropicBackendFactory(settings),
    )
    return run_interactive(service.open_session(args.project))


def run_interactive(session) -> int:
    """Run the legacy terminal conversation loop for a prepared session."""
    print(f"Conversion Guidance Agent — client: {session.project.name} (Ctrl-D to exit)")
    while True:
        try:
            question = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if question:
            print("\nagent> " + session.ask(question))
