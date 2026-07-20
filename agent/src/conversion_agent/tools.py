"""The agent's tool surface (Phase 1).

All tools are read-only. Each returns a compact string the model can cite.
The active ProjectContext is set once per session by the CLI/service layer.
"""

from __future__ import annotations

import json

from anthropic import beta_tool

from . import knowledge
from .config import ProjectContext, load_dictionary

_project: ProjectContext | None = None


def set_project(project: ProjectContext) -> None:
    global _project
    _project = project


def _require_project() -> ProjectContext:
    if _project is None:
        raise RuntimeError("No project context loaded — call set_project() first.")
    return _project


@beta_tool
def search_knowledge_base(query: str) -> str:
    """Search the conversion knowledge base (process playbook, DCT guides,
    past-project decisions). Call this before answering any question about
    methodology, best practices, or how something was handled previously.

    Args:
        query: Search terms describing what you need to know.
    """
    chunks = knowledge.search(query)
    if not chunks:
        return "No knowledge-base results. Say you don't know and escalate."
    out = []
    for c in chunks:
        out.append(f"[source: {c.source} § {c.heading}]\n{c.text}")
    return "\n\n---\n\n".join(out)


@beta_tool
def lookup_dct_field(table: str = "", column: str = "", module: str = "") -> str:
    """Look up the Data Conversion Template (DCT) data dictionary. Call this
    whenever a question involves what the DCT expects: a table's columns and
    types, whether a column is nullable, its max length, or which tables a
    module contains.

    Args:
        table: DCT table name, e.g. "permit" or "business_license". Case-insensitive.
        column: Optional column name to narrow the lookup to one column.
        module: Alternative to table — list a module's tables, e.g. "permits",
            "code_enforcement", "business_license", "contacts", "finance".
    """
    dictionary = load_dictionary()
    tables = dictionary.get("tables", {})
    if module and not table:
        hits = {n: e.get("description", "") for n, e in tables.items()
                if e.get("module") == module.strip().lower()}
        if not hits:
            mods = sorted({e.get("module", "") for e in tables.values()})
            return f"No module '{module}'. Modules: {mods}"
        return json.dumps({"module": module, "tables": hits}, indent=2)
    key = table.strip().lower()
    entry = tables.get(key)
    if entry is None:
        near = [n for n in tables if key and key in n]
        return f"Table '{table}' not in dictionary (DCT {dictionary.get('version')}). Close matches: {near[:15]}"
    if not column:
        return json.dumps({"table": key, "module": entry.get("module"),
                           "description": entry.get("description", ""),
                           "columns": entry.get("columns", {})}, indent=2)
    col = entry.get("columns", {}).get(column.strip().lower())
    if col is None:
        return f"Column '{column}' not in {key}. Columns: {sorted(entry.get('columns', {}))}"
    return json.dumps({"table": key, "column": column.strip().lower(), **col}, indent=2)


@beta_tool
def get_mapping_status(status_filter: str = "") -> str:
    """Read the current client's source-to-target mapping workbook. Call this
    for questions about mapping progress, what is blocked on configuration,
    or how a specific legacy field is mapped.

    Args:
        status_filter: Optional status to filter on: "draft", "confirmed",
            or "blocked-on-config". Empty returns summary counts plus all rows.
    """
    project = _require_project()
    rows = project.mapping_rows
    if status_filter:
        rows = [r for r in rows if r.get("status", "").strip().lower() == status_filter.strip().lower()]
    summary = {"client": project.name, "status_counts": project.mapping_status_counts, "rows": rows}
    return json.dumps(summary, indent=2)


@beta_tool
def get_profile_summary(entity: str = "") -> str:
    """Read the client's legacy-data profiling summary (volumes, null rates,
    data-quality findings per entity) produced by the profiling suite. Call
    this for questions about the client's current-state data.

    Args:
        entity: Optional entity name to narrow the result, e.g. "permits".
    """
    project = _require_project()
    profile = project.profile_summary
    if not profile:
        return "No profiling summary loaded for this client yet."
    if entity:
        entities = profile.get("entities", {})
        match = entities.get(entity.lower())
        if match is None:
            return f"No profile for entity '{entity}'. Known: {sorted(entities)}"
        return json.dumps({entity.lower(): match}, indent=2)
    return json.dumps(profile, indent=2)


ALL_TOOLS = [search_knowledge_base, lookup_dct_field, get_mapping_status, get_profile_summary]
