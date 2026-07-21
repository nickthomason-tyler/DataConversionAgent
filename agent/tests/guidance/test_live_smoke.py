"""Credential-gated smoke tests for the production guidance backends."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.backends import AnthropicBackendFactory
from conversion_agent.guidance.service import GuidanceService
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog


AGENT_ROOT = Path(__file__).parents[2]
SMOKE_PROJECTS_ROOT = AGENT_ROOT / "clients"


def _service(backend: str) -> GuidanceService:
    settings = AppSettings.from_sources(
        projects_root=SMOKE_PROJECTS_ROOT,
        environ={**os.environ, "CONVERSION_AGENT_BACKEND": backend},
        development_root=SMOKE_PROJECTS_ROOT,
    )
    assert settings.projects_root is not None
    return GuidanceService(
        settings,
        FilesystemProjectRepository(settings.projects_root),
        ResourceCatalog(),
        AnthropicBackendFactory(settings),
    )


def test_live_smoke_service_ignores_ambient_projects_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONVERSION_AGENT_PROJECTS_ROOT", str(tmp_path / "real-client-projects"))

    service = _service("anthropic")

    assert service.settings.projects_root == SMOKE_PROJECTS_ROOT.resolve()
    assert service.repository.root == SMOKE_PROJECTS_ROOT.resolve()


@pytest.mark.live
def test_live_anthropic_guidance_service_smoke() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("Set ANTHROPIC_API_KEY to run the Anthropic live smoke test.")

    answer = (
        _service("anthropic")
        .open_session("example-client")
        .ask("Reply with a brief live smoke acknowledgement.")
    )

    assert answer.strip()


@pytest.mark.parametrize("opt_in", [None, "", "0", "false", " False "])
def test_bedrock_smoke_skips_before_service_without_exact_opt_in(monkeypatch, opt_in) -> None:
    if opt_in is None:
        monkeypatch.delenv("CONVERSION_AGENT_LIVE_BEDROCK", raising=False)
    else:
        monkeypatch.setenv("CONVERSION_AGENT_LIVE_BEDROCK", opt_in)
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    def fail_if_constructed(_: str) -> GuidanceService:
        pytest.fail("Bedrock service construction must not happen without an exact opt-in")

    monkeypatch.setattr(sys.modules[__name__], "_service", fail_if_constructed)

    with pytest.raises(pytest.skip.Exception):
        test_live_bedrock_guidance_service_smoke()


@pytest.mark.live
def test_live_bedrock_guidance_service_smoke() -> None:
    if os.environ.get("CONVERSION_AGENT_LIVE_BEDROCK", "").strip() != "1":
        pytest.skip("Set CONVERSION_AGENT_LIVE_BEDROCK=1 to run the Bedrock live smoke test.")
    if not os.environ.get("AWS_REGION"):
        pytest.skip("Set AWS_REGION for the Bedrock live smoke test.")

    answer = (
        _service("bedrock")
        .open_session("example-client")
        .ask("Reply with a brief live smoke acknowledgement.")
    )

    assert answer.strip()
