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


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"backend": "unsupported"}, "backend"),
        ({"model": "   "}, "model"),
        ({"backend_retries": -1}, "backend_retries"),
        ({"max_history_messages": 1}, "max_history_messages"),
        ({"max_tool_chars": 79}, "max_tool_chars"),
    ],
)
def test_rejects_invalid_backend_model_retry_and_pair_capacity(
    tmp_path: Path, overrides: dict, message: str
) -> None:
    with pytest.raises(SettingsError, match=message):
        AppSettings(projects_root=tmp_path, **overrides)


def test_parses_backend_retries_and_normalizes_backend_and_model(tmp_path: Path) -> None:
    settings = AppSettings.from_sources(
        projects_root=tmp_path,
        environ={
            "CONVERSION_AGENT_BACKEND": " Bedrock ",
            "CONVERSION_AGENT_MODEL": " model-id ",
            "CONVERSION_AGENT_BACKEND_RETRIES": "3",
        },
    )

    assert settings.backend == "bedrock"
    assert settings.model == "model-id"
    assert settings.backend_retries == 3
