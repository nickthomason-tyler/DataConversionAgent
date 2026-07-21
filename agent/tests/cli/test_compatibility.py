"""Public command-line compatibility tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conversion_agent.core.errors import (
    BackendError,
    OutputError,
    ProjectValidationError,
    SettingsError,
    WorkbookError,
)


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
    ("error", "exit_code"),
    [
        (SettingsError("bad settings"), 2),
        (ProjectValidationError("bad project"), 3),
        (WorkbookError("bad workbook"), 4),
        (BackendError("bad backend"), 5),
        (OutputError("bad output"), 6),
    ],
)
def test_shared_cli_errors_use_exact_stable_exit_codes(error, exit_code, capsys) -> None:
    from conversion_agent.cli.common import render_error

    assert render_error(error) == exit_code
    assert "Traceback" not in capsys.readouterr().err


def test_non_debug_error_hides_cause_while_debug_keeps_traceback(capsys) -> None:
    from conversion_agent.cli.common import render_error

    try:
        raise RuntimeError("underlying detail")
    except RuntimeError as cause:
        error = BackendError("backend unavailable")
        error.__cause__ = cause

    assert render_error(error) == 5
    concise = capsys.readouterr().err
    assert "backend unavailable" in concise
    assert "underlying detail" not in concise
    assert "Traceback" not in concise

    assert render_error(error, debug=True) == 5
    debug = capsys.readouterr().err
    assert "underlying detail" in debug
    assert "Traceback" in debug


@pytest.mark.parametrize("entrypoint", ["new", "legacy"])
def test_malformed_apply_json_uses_validation_exit_four(
    monkeypatch, tmp_path: Path, entrypoint: str
) -> None:
    from conversion_agent.cli import apply as new_apply
    from conversion_agent.mapping import apply as legacy_apply

    proposals = tmp_path / "proposals.json"
    proposals.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(new_apply, "load_validated_workbook", lambda _: object())
    main = new_apply.main if entrypoint == "new" else legacy_apply.main

    assert main(["input.xlsx", str(proposals), "output.xlsx"]) == 4


@pytest.mark.parametrize("entrypoint", ["new", "legacy"])
def test_invalid_mapping_rules_use_config_exit_two(tmp_path: Path, entrypoint: str) -> None:
    from conversion_agent.cli import mapping as new_mapping
    from conversion_agent.mapping import cli as legacy_mapping

    rules = tmp_path / "rules.yaml"
    rules.write_text("token_map: [not, an, object]", encoding="utf-8")
    main = new_mapping.main if entrypoint == "new" else legacy_mapping.main

    assert main(["input.xlsx", "output.xlsx", "--rules", str(rules)]) == 2


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
