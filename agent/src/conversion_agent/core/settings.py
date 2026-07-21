"""Validated application settings assembled from explicit and environment sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import SettingsError


@dataclass(frozen=True)
class AppSettings:
    projects_root: Path | None
    backend: str = "anthropic"
    model: str = "claude-opus-4-8"
    max_history_messages: int = 40
    max_tool_chars: int = 50_000
    mapping_default_limit: int = 100
    mapping_max_limit: int = 500
    backend_retries: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or self.backend.strip().lower() not in {
            "anthropic",
            "bedrock",
        }:
            raise SettingsError("backend must be 'anthropic' or 'bedrock'")
        if not isinstance(self.model, str) or not self.model.strip():
            raise SettingsError("model must not be blank")
        object.__setattr__(self, "backend", self.backend.strip().lower())
        object.__setattr__(self, "model", self.model.strip())
        if self.max_history_messages < 2:
            raise SettingsError("max_history_messages must be at least 2 to retain message pairs")
        if self.max_tool_chars < 80:
            raise SettingsError("max_tool_chars must be at least 80 for truncation metadata")
        for name in (
            "mapping_default_limit",
            "mapping_max_limit",
        ):
            if getattr(self, name) <= 0:
                raise SettingsError(f"{name} must be greater than zero")
        if self.mapping_default_limit > self.mapping_max_limit:
            raise SettingsError("mapping_default_limit cannot exceed mapping_max_limit")
        if self.backend_retries < 0:
            raise SettingsError("backend_retries must be zero or greater")

    @classmethod
    def from_sources(
        cls,
        *,
        projects_root: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
        development_root: Path | None = None,
        require_projects: bool = True,
    ) -> "AppSettings":
        env = dict(environ) if environ is not None else {}
        root_value = (
            projects_root
            if projects_root is not None
            else env.get("CONVERSION_AGENT_PROJECTS_ROOT") or development_root
        )
        if root_value is None and require_projects:
            raise SettingsError("Set --projects-root or CONVERSION_AGENT_PROJECTS_ROOT.")
        try:
            numeric = {
                "max_history_messages": int(env.get("CONVERSION_AGENT_MAX_HISTORY_MESSAGES", "40")),
                "max_tool_chars": int(env.get("CONVERSION_AGENT_MAX_TOOL_CHARS", "50000")),
                "mapping_default_limit": int(
                    env.get("CONVERSION_AGENT_MAPPING_DEFAULT_LIMIT", "100")
                ),
                "mapping_max_limit": int(env.get("CONVERSION_AGENT_MAPPING_MAX_LIMIT", "500")),
                "backend_retries": int(env.get("CONVERSION_AGENT_BACKEND_RETRIES", "2")),
            }
        except (TypeError, ValueError) as exc:
            raise SettingsError(f"Invalid integer setting: {exc}") from exc
        return cls(
            projects_root=Path(root_value).expanduser().resolve()
            if root_value is not None
            else None,
            backend=env.get("CONVERSION_AGENT_BACKEND", "anthropic"),
            model=env.get("CONVERSION_AGENT_MODEL", "claude-opus-4-8"),
            **numeric,
        )
