from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out)],
        check=True,
    )
    return next(out.glob("*.whl"))


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    project = root / "alpha"
    project.mkdir(parents=True)
    (project / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "client_name": "Alpha City",
                "source_system": "Legacy Alpha",
                "phase": "Mock 1",
                "in_scope_entities": ["permits"],
            }
        ),
        encoding="utf-8",
    )
    with (project / "mapping_workbook.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_table",
                "source_column",
                "target_table",
                "target_column",
                "rule",
                "status",
                "owner",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_table": "PERMITS",
                "source_column": "TYPE",
                "target_table": "permit",
                "target_column": "permit_type",
                "rule": "crosswalk",
                "status": "draft",
                "owner": "analyst",
            }
        )
    (project / "profile_summary.json").write_text(
        json.dumps({"entities": {"permits": {"row_count": 10}}}), encoding="utf-8"
    )
    return root


@pytest.fixture
def two_project_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    for project_id, client_name, source_system in (
        ("alpha", "Alpha City", "Legacy Alpha"),
        ("beta", "Beta City", "Legacy Beta"),
    ):
        project = root / project_id
        project.mkdir(parents=True)
        (project / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "client_name": client_name,
                    "source_system": source_system,
                    "phase": "Mock 1",
                    "in_scope_entities": ["permits"],
                }
            ),
            encoding="utf-8",
        )
        with (project / "mapping_workbook.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "source_table",
                    "source_column",
                    "target_table",
                    "target_column",
                    "rule",
                    "status",
                    "owner",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "source_table": "PERMITS",
                    "source_column": "TYPE",
                    "target_table": "permit",
                    "target_column": "permit_type",
                    "rule": "crosswalk",
                    "status": "draft",
                    "owner": "analyst",
                }
            )
        (project / "profile_summary.json").write_text(
            json.dumps({"entities": {"permits": {"row_count": 10}}}), encoding="utf-8"
        )
    return root
