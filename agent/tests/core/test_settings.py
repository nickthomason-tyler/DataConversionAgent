from pathlib import Path

import pytest

from conversion_agent.core.errors import SettingsError
from conversion_agent.core.settings import AppSettings


def test_explicit_project_root_wins_over_environment(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    env = tmp_path / "env"
    settings = AppSettings.from_sources(
        projects_root=explicit,
        environ={"CONVERSION_AGENT_PROJECTS_ROOT": str(env)},
        development_root=None,
    )
    assert settings.projects_root == explicit.resolve()
    assert settings.max_history_messages == 40
    assert settings.max_tool_chars == 50_000


def test_rejects_nonpositive_history_limit(tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="max_history_messages"):
        AppSettings.from_sources(
            projects_root=tmp_path,
            environ={"CONVERSION_AGENT_MAX_HISTORY_MESSAGES": "0"},
        )
