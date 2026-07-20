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
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
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
import conversion_agent
catalog = ResourceCatalog()
assert catalog.dictionary()["table_count"] == 309
print(conversion_agent.__file__)
"""
    result = subprocess.run(
        [str(python), "-c", code],
        cwd=outside,
        check=True,
        text=True,
        capture_output=True,
        env=child_env,
    )
    assert str(environment) in result.stdout
