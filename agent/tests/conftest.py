from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml


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
