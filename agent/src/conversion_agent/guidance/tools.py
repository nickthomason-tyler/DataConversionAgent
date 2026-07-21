"""Project-bound tool handlers for a single guidance session."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from anthropic import beta_tool

from conversion_agent.projects.models import ProjectContext, to_json_compatible


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _bounded_json(
    value: object,
    *,
    limit: int,
    rows_truncated: bool = False,
    characters_truncated: bool = False,
) -> str:
    """Serialize valid JSON with explicit truncation metadata within ``limit``."""
    compatible = to_json_compatible(value)
    if isinstance(compatible, dict):
        payload = dict(compatible)
    else:
        payload = {"result": compatible}
    payload["truncation"] = {
        "rows": rows_truncated,
        "characters": characters_truncated,
        "character_limit": limit,
    }
    rendered = _compact_json(payload)
    if len(rendered) <= limit:
        return rendered

    metadata = {
        "rows": rows_truncated,
        "characters": True,
        "character_limit": limit,
    }
    original = _compact_json(compatible)
    marker = "...[TRUNCATED]"
    low = 0
    high = len(original)
    best = _compact_json({"preview": marker, "truncation": metadata})
    while low <= high:
        middle = (low + high) // 2
        candidate = _compact_json({"preview": original[:middle] + marker, "truncation": metadata})
        if len(candidate) <= limit:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    if len(best) <= limit:
        return best
    minimal = _compact_json({"truncation": metadata})
    if len(minimal) <= limit:
        return minimal
    fallback = _compact_json({"truncated": True})
    if len(fallback) <= limit:
        return fallback
    if limit >= 4:
        return "null"
    return "{}" if limit >= 2 else "0"


def _bounded_knowledge(hits: list[Any], limit: int) -> str:
    blocks = [f"{hit.citation}\n{hit.text}" for hit in hits]
    rendered = "\n\n---\n\n".join(blocks)
    if len(rendered) <= limit:
        return rendered

    detailed_marker = f"[TRUNCATED: tool output exceeded {limit} characters]"
    marker = detailed_marker if len(detailed_marker) <= limit else "[TRUNCATED]"
    citation = hits[0].citation
    fixed = f"{citation}\n\n{marker}"
    if len(fixed) > limit:
        return marker if len(marker) <= limit else marker[:limit]
    text_budget = limit - len(fixed) - 1
    preview = hits[0].text[: max(0, text_budget)]
    return f"{citation}\n{preview}\n{marker}"


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
        return _bounded_knowledge(hits, settings.max_tool_chars)

    def get_mapping_status(
        status_filter: str = "", limit: int | None = None, offset: int = 0
    ) -> str:
        """Return a bounded page of active-project source-to-target mappings."""
        if limit is None:
            limit = settings.mapping_default_limit
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
        rendered = _bounded_json(
            payload,
            limit=settings.max_tool_chars,
            rows_truncated=bool(payload["truncated"]),
        )
        if len(rendered) <= settings.max_tool_chars and json.loads(rendered).get(
            "truncation", {}
        ).get("characters"):
            while page:
                page.pop()
                payload["rows"] = [asdict(row) for row in page]
                payload["returned"] = len(page)
                payload["truncated"] = True
                rendered = _bounded_json(
                    payload,
                    limit=settings.max_tool_chars,
                    rows_truncated=True,
                    characters_truncated=True,
                )
                if "preview" not in json.loads(rendered):
                    break
        return rendered

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
        return _bounded_json(value, limit=settings.max_tool_chars)

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
        return _bounded_json(profile, limit=settings.max_tool_chars)

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
