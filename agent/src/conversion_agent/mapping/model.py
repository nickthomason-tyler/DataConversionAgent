"""Data model for tool-generated lookup crosswalk workbooks.

The conversion tool emits one visible tab per module (sections of legacy
values with empty destination columns), a paired "<Tab> Hidden" tab holding
the valid destination pick lists (including cascading constraints), and a
LookupSpec tab embedding a JSON contract of source/destination tables.
This model is generator-shaped, not client-shaped: it works for any client
workbook produced by the same tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class SourceRow:
    row_idx: int  # 1-based row in the visible tab
    values: tuple[str, ...]  # source cell values, one per source column
    existing: tuple[str, ...]  # current destination cell values ("" if empty)


@dataclass
class Proposal:
    dest: tuple[str, ...]  # proposed destination values, one per dest column
    method: str  # e.g. "exact", "normalized", "abbrev", "llm"
    confidence: float  # 1.0 for deterministic lanes
    note: str = ""


@dataclass
class Section:
    tab: str
    title: str
    src_cols: list[int]  # 1-based column indices of source columns
    dst_cols: list[int]  # 1-based column indices of destination columns
    notes_col: int | None
    header_row: int  # row with column headers
    rows: list[SourceRow] = field(default_factory=list)
    dest_lists: list[list[str]] = field(default_factory=list)  # one list per dest col
    cascade: dict[str, list[str]] = field(
        default_factory=dict
    )  # dest col1 value -> valid col2 values
    proposals: dict[int, Proposal] = field(default_factory=dict)  # row_idx -> proposal

    @property
    def key(self) -> str:
        return f"{self.tab}::{self.title}"

    @property
    def unmatched(self) -> list[SourceRow]:
        return [
            r
            for r in self.rows
            if r.row_idx not in self.proposals and not any(v.strip() for v in r.existing)
        ]


@dataclass
class CrosswalkWorkbook:
    path: str
    spec: dict  # parsed LookupSpec JSON
    sections: list[Section] = field(default_factory=list)

    def section(self, tab: str, title: str) -> Section | None:
        for s in self.sections:
            if s.tab == tab and s.title == title:
                return s
        return None


@dataclass(frozen=True)
class WriteReport:
    """Verified write-back totals, with legacy row-count accessors."""

    deterministic_rows: int
    model_rows: int
    destination_cells: int
    note_cells: int
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, int]:
        """Return the legacy report shape used by direct callers."""
        return {"auto": self.deterministic_rows, "llm": self.model_rows}

    def __getitem__(self, key: str) -> int:
        return self.as_dict()[key]

    def get(self, key: str, default: int | None = None) -> int | None:
        return self.as_dict().get(key, default)

    def keys(self) -> Iterator[str]:
        return iter(("auto", "llm"))


@dataclass(frozen=True)
class CellEdit:
    sheet_path: str
    cell_ref: str
    value: str
