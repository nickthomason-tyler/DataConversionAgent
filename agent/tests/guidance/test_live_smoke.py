"""Credential-gated smoke tests for the production guidance backends."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.backends import AnthropicBackendFactory
from conversion_agent.guidance.service import GuidanceService
from conversion_agent.projects.filesystem import FilesystemProjectRepository
from conversion_agent.resources.catalog import ResourceCatalog


AGENT_ROOT = Path(__file__).parents[2]


def _service(backend: str) -> GuidanceService:
    settings = AppSettings.from_sources(
        environ={**os.environ, "CONVERSION_AGENT_BACKEND": backend},
        development_root=AGENT_ROOT / "clients",
    )
    assert settings.projects_root is not None
    return GuidanceService(
        settings,
        FilesystemProjectRepository(settings.projects_root),
        ResourceCatalog(),
        AnthropicBackendFactory(settings),
    )


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


@pytest.mark.live
def test_live_bedrock_guidance_service_smoke() -> None:
    if not os.environ.get("CONVERSION_AGENT_LIVE_BEDROCK"):
        pytest.skip("Set CONVERSION_AGENT_LIVE_BEDROCK=1 to run the Bedrock live smoke test.")
    if not os.environ.get("AWS_REGION"):
        pytest.skip("Set AWS_REGION for the Bedrock live smoke test.")

    answer = (
        _service("bedrock")
        .open_session("example-client")
        .ask("Reply with a brief live smoke acknowledgement.")
    )

    assert answer.strip()
