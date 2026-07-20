"""Injected model backends and retry behavior for guidance sessions."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Protocol, TypeVar

import anthropic

from conversion_agent.core.settings import AppSettings

T = TypeVar("T")


class ModelBackendFactory(Protocol):
    @property
    def model_id(self) -> str: ...

    def create(self) -> object: ...


class AnthropicBackendFactory:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def create(self):
        if self.settings.backend == "bedrock":
            from anthropic import AnthropicBedrockMantle

            return AnthropicBedrockMantle(aws_region=os.environ.get("AWS_REGION", "us-east-1"))
        return anthropic.Anthropic()

    @property
    def model_id(self) -> str:
        prefix = "anthropic." if self.settings.backend == "bedrock" else ""
        return f"{prefix}{self.settings.model}"


def is_transient_backend_error(exc: Exception) -> bool:
    return isinstance(
        exc,
        (
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
        ),
    )


def run_with_retries(
    operation: Callable[[], T],
    *,
    retries: int,
    is_transient: Callable[[Exception], bool] = is_transient_backend_error,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    for attempt in range(retries + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == retries or not is_transient(exc):
                raise
            sleep(2**attempt)
    raise AssertionError("retry loop exited unexpectedly")
