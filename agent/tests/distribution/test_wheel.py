from __future__ import annotations

import os
from pathlib import Path
import subprocess
import venv
from zipfile import ZipFile


def test_built_wheel_contains_runtime_resources(built_wheel: Path) -> None:
    with ZipFile(built_wheel) as wheel:
        names = set(wheel.namelist())

    assert "conversion_agent/resources/data/dct/dictionary.yaml" in names
    assert any(name.endswith("resources/data/knowledge/playbook/README.md") for name in names)

    metadata = next(name for name in names if name.endswith(".dist-info/entry_points.txt"))
    with ZipFile(built_wheel) as wheel:
        entry_points = wheel.read(metadata).decode()

    assert "conversion-agent" in entry_points
    assert "conversion-map" in entry_points
    assert "conversion-apply" in entry_points


def test_wheel_loads_resources_outside_checkout(built_wheel: Path, tmp_path: Path) -> None:
    environment = tmp_path / "venv"
    outside = tmp_path / "outside"
    outside.mkdir()
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(built_wheel)],
        check=True,
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
    )
    assert str(environment) in result.stdout
