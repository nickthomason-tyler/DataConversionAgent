"""Mapping pipeline command adapter."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

import yaml

from conversion_agent.config import CLIENTS_DIR
from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.backends import AnthropicBackendFactory
from conversion_agent.mapping.service import MappingReport, MappingRequest, MappingService
from conversion_agent.projects.filesystem import FilesystemProjectRepository

from .common import render_error


def build_parser() -> argparse.ArgumentParser:
    """Build the mapping parser while retaining its established arguments."""
    parser = argparse.ArgumentParser(prog="conversion-map")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--rules")
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--project")
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
        require_projects=bool(args.project),
    )
    repository = (
        FilesystemProjectRepository(settings.projects_root)
        if args.project and settings.projects_root is not None
        else None
    )
    rules = _load_rules(args.rules)
    service = MappingService(
        repository=repository,
        backend_factory=AnthropicBackendFactory(settings) if args.llm else None,
    )
    report = service.run(
        MappingRequest(
            input_path=Path(args.input),
            output_path=Path(args.output),
            token_map=rules.get("token_map", {}),
            use_llm=args.llm,
            project_id=args.project,
        )
    )
    print(format_mapping_report(report))
    return 0


def _load_rules(path: str | None) -> dict:
    if path is None:
        return {}
    rules = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if rules is None:
        return {}
    if not isinstance(rules, dict):
        raise ValueError("Mapping rules must be a YAML object.")
    token_map = rules.get("token_map", {})
    if not isinstance(token_map, dict):
        raise ValueError("Mapping rules token_map must be an object.")
    return rules


def format_mapping_report(report: MappingReport) -> str:
    """Render the typed report produced by ``MappingService``."""
    lines = [
        "Mapping complete:",
        f"  rows: {report.rows}",
        f"  pre-mapped: {report.premapped}",
        f"  deterministic: {report.deterministic}",
        f"  model-proposed: {report.model_proposed}",
        f"  remaining: {report.remaining}",
    ]
    lines.extend(f"  warning: {warning}" for warning in report.warnings)
    return "\n".join(lines)
