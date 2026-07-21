"""Compatibility helpers for the injected guidance backend factory."""

from __future__ import annotations

import os

from .core.settings import AppSettings
from .guidance.backends import AnthropicBackendFactory


def _settings() -> AppSettings:
    return AppSettings.from_sources(
        environ=os.environ,
        development_root=None,
        require_projects=False,
    )


def is_bedrock() -> bool:
    return _settings().backend == "bedrock"


def model_id() -> str:
    return AnthropicBackendFactory(_settings()).model_id


def make_client():
    return AnthropicBackendFactory(_settings()).create()
