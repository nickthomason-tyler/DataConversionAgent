"""Per-client project context.

Each client project lives under agent/clients/<name>/ and carries the three
artifacts the agent is grounded in: the project file, the mapping workbook,
and the profiling summary produced by the toolkit's profiling suite.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

AGENT_ROOT = Path(__file__).resolve().parents[2]
CLIENTS_DIR = AGENT_ROOT / "clients"
KNOWLEDGE_DIR = AGENT_ROOT / "knowledge"
DICTIONARY_PATH = AGENT_ROOT / "dct" / "dictionary.yaml"


@dataclass
class ProjectContext:
    name: str
    project: dict
    mapping_rows: list[dict] = field(default_factory=list)
    profile_summary: dict = field(default_factory=dict)

    @property
    def mapping_status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.mapping_rows:
            status = row.get("status", "unknown").strip().lower()
            counts[status] = counts.get(status, 0) + 1
        return counts


def load_project(client_name: str) -> ProjectContext:
    client_dir = CLIENTS_DIR / client_name
    project_file = client_dir / "project.yaml"
    if not project_file.exists():
        available = sorted(p.name for p in CLIENTS_DIR.iterdir() if p.is_dir())
        raise FileNotFoundError(
            f"No project.yaml for client '{client_name}'. Available: {available}"
        )

    project = yaml.safe_load(project_file.read_text())

    mapping_rows: list[dict] = []
    workbook = client_dir / "mapping_workbook.csv"
    if workbook.exists():
        with workbook.open(newline="") as f:
            mapping_rows = list(csv.DictReader(f))

    profile_summary: dict = {}
    profile = client_dir / "profile_summary.json"
    if profile.exists():
        profile_summary = json.loads(profile.read_text())

    return ProjectContext(
        name=client_name,
        project=project,
        mapping_rows=mapping_rows,
        profile_summary=profile_summary,
    )


def load_dictionary() -> dict:
    return yaml.safe_load(DICTIONARY_PATH.read_text())
