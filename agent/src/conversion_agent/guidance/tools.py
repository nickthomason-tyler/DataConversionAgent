"""Project-bound tool handlers for a single guidance session."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from anthropic import beta_tool

from conversion_agent.projects.models import ProjectContext, to_json_compatible


@dataclass(frozen=True)
class BoundToolSet:
    """Anthropic tool definitions paired with handlers closed over one project."""

    anthropic_tools: tuple[object, ...]
    handlers: Mapping[str, Callable[..., str]]

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        return self.handlers[name](**arguments)


def build_tools(
    project: ProjectContext,
    knowledge_index,
    dictionary: Mapping[str, Any],
    settings,
) -> BoundToolSet:
    """Build a read-only tool set whose closures cannot switch projects."""

    def search_knowledge_base(query: str) -> str:
        """Search shared and active-project conversion knowledge for a query."""
        hits = knowledge_index.search(query)
        if not hits:
            return "No knowledge-base results. Say you don't know and escalate."
        return "\n\n---\n\n".join(f"{hit.citation}\n{hit.text}" for hit in hits)[
            : settings.max_tool_chars
        ]

    def get_mapping_status(status_filter: str = "", limit: int = 100, offset: int = 0) -> str:
        """Return a bounded page of active-project source-to-target mappings."""
        limit = max(1, min(limit, settings.mapping_max_limit))
        offset = max(0, offset)
        rows = [
            row
            for row in project.mapping_rows
            if not status_filter or row.status.strip().lower() == status_filter.strip().lower()
        ]
        page = rows[offset : offset + limit]
        payload = {
            "client": project.metadata.client_name,
            "status_counts": project.mapping_status_counts,
            "offset": offset,
            "returned": len(page),
            "total": len(rows),
            "truncated": offset + len(page) < len(rows),
            "rows": [asdict(row) for row in page],
        }
        return json.dumps(payload, indent=2)[: settings.max_tool_chars]

    def lookup_dct_field(table: str = "", column: str = "", module: str = "") -> str:
        """Look up DCT table, column, or module metadata from the dictionary."""
        tables = dictionary.get("tables", {})
        if module and not table:
            hits = {
                name: entry.get("description", "")
                for name, entry in tables.items()
                if entry.get("module") == module.strip().lower()
            }
            value: dict[str, Any] = {"module": module, "tables": hits}
        else:
            key = table.strip().lower()
            entry = tables.get(key)
            if entry is None:
                near = [name for name in tables if key and key in name]
                return f"Table '{table}' not in dictionary. Close matches: {near[:15]}"
            if column:
                col_key = column.strip().lower()
                col = entry.get("columns", {}).get(col_key)
                if col is None:
                    return f"Column '{column}' not in {key}."
                value = {"table": key, "column": col_key, **col}
            else:
                value = {"table": key, **entry}
        return json.dumps(to_json_compatible(value), indent=2)[: settings.max_tool_chars]

    def get_profile_summary(entity: str = "") -> str:
        """Return profiling results for the active project, optionally one entity."""
        profile = project.profile_summary
        if not profile:
            return "No profiling summary loaded for this client yet."
        if entity:
            entities = profile.get("entities", {})
            match = entities.get(entity.lower())
            if match is None:
                return f"No profile for entity '{entity}'. Known: {sorted(entities)}"
            profile = {entity.lower(): match}
        return json.dumps(to_json_compatible(profile), indent=2)[: settings.max_tool_chars]

    handlers: dict[str, Callable[..., str]] = {
        "search_knowledge_base": search_knowledge_base,
        "lookup_dct_field": lookup_dct_field,
        "get_mapping_status": get_mapping_status,
        "get_profile_summary": get_profile_summary,
    }
    return BoundToolSet(
        anthropic_tools=tuple(beta_tool(handler) for handler in handlers.values()),
        handlers=handlers,
    )
