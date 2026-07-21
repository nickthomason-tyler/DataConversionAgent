from __future__ import annotations

from configparser import ConfigParser
import os
from pathlib import Path
import subprocess
import venv
from zipfile import ZipFile


def test_built_wheel_contains_runtime_resources(built_wheel: Path) -> None:
    with ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())

    resource_names = {name for name in names if name.startswith("conversion_agent/resources/data/")}
    assert resource_names == {
        "conversion_agent/resources/data/dct/dictionary.yaml",
        "conversion_agent/resources/data/knowledge/README.md",
        "conversion_agent/resources/data/knowledge/decisions/duplicate-contact-survivorship.md",
        "conversion_agent/resources/data/knowledge/decisions/sentinel-dates.md",
        "conversion_agent/resources/data/knowledge/playbook/01-early-data-analysis.md",
        "conversion_agent/resources/data/knowledge/playbook/02-initial-etl-migration.md",
        "conversion_agent/resources/data/knowledge/playbook/03-conversion-agent.md",
        "conversion_agent/resources/data/knowledge/playbook/04-launch-playbook.md",
        "conversion_agent/resources/data/knowledge/playbook/README.md",
    }

    metadata = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
    with ZipFile(built_wheel) as wheel:
        entry_points = wheel.read(metadata).decode()

    parser = ConfigParser()
    parser.read_string(entry_points)
    assert dict(parser["console_scripts"]) == {
        "conversion-agent": "conversion_agent.cli.guidance:main",
        "conversion-map": "conversion_agent.cli.mapping:main",
        "conversion-apply": "conversion_agent.cli.apply:main",
    }


def test_wheel_loads_resources_outside_checkout(built_wheel: Path, tmp_path: Path) -> None:
    environment = tmp_path / "venv"
    outside = tmp_path / "outside"
    outside.mkdir()
    projects = outside / "projects"
    external_project = projects / "external-client"
    external_project.mkdir(parents=True)
    (external_project / "project.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "client_name: External Client",
                "source_system: External Legacy",
                "phase: Mock 1",
                "in_scope_entities: [permits]",
            ]
        ),
        encoding="utf-8",
    )
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    child_env = {
        **os.environ,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INDEX": "1",
    }
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(built_wheel)],
        check=True,
        env=child_env,
    )
    code = """
import conversion_agent.resources
from conversion_agent.resources.catalog import ResourceCatalog
from conversion_agent.config import load_project
import conversion_agent
import sys
catalog = ResourceCatalog()
assert catalog.dictionary()["table_count"] == 309
project = load_project("external-client", projects_root=sys.argv[1])
assert project.metadata.client_name == "External Client"
print(conversion_agent.__file__)
"""
    result = subprocess.run(
        [str(python), "-c", code, str(projects)],
        cwd=outside,
        check=True,
        text=True,
        capture_output=True,
        env=child_env,
    )
    assert str(environment) in result.stdout

    for command, usage in (
        ("conversion-agent", "usage: conversion-agent"),
        ("conversion-map", "usage: conversion-map"),
        ("conversion-apply", "usage: conversion-apply"),
    ):
        executable = scripts / (f"{command}.exe" if os.name == "nt" else command)
        help_result = subprocess.run(
            [str(executable), "--help"],
            cwd=outside,
            env=child_env,
            check=False,
            text=True,
            capture_output=True,
        )
        assert help_result.returncode == 0, help_result.stderr
        assert usage in help_result.stdout
