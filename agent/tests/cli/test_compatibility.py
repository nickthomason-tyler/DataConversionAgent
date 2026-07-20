"""Public command-line compatibility tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conversion_agent.core.errors import ProjectValidationError


def test_guidance_keeps_project_positional_argument() -> None:
    from conversion_agent.cli.guidance import build_parser

    args = build_parser().parse_args(["example-client"])

    assert args.project == "example-client"


def test_mapping_keeps_existing_positional_and_flags() -> None:
    from conversion_agent.cli.mapping import build_parser

    args = build_parser().parse_args(["in.xlsx", "out.xlsx", "--rules", "rules.yaml", "--llm"])

    assert args.input == "in.xlsx"
    assert args.output == "out.xlsx"
    assert args.rules == "rules.yaml"
    assert args.llm is True


def test_new_project_root_flag_is_additive() -> None:
    from conversion_agent.cli.guidance import build_parser

    args = build_parser().parse_args(["alpha", "--projects-root", "/projects"])

    assert args.projects_root == "/projects"


def test_project_error_uses_stable_exit_code(capsys) -> None:
    from conversion_agent.cli.common import render_error

    code = render_error(ProjectValidationError("bad project"))

    assert code == 3
    assert "bad project" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module", "usage"),
    [
        ("conversion_agent.cli", "usage: conversion-agent"),
        ("conversion_agent.mapping.cli", "usage: conversion-map"),
        ("conversion_agent.mapping.apply", "usage: conversion-apply"),
    ],
)
def test_module_help_requires_no_project_configuration(module: str, usage: str) -> None:
    agent_root = Path(__file__).parents[2]
    environment = {**os.environ, "PYTHONPATH": str(agent_root / "src")}

    completed = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=agent_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert usage in completed.stdout
