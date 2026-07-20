"""Backend selection: first-party Claude API or Amazon Bedrock.

Set CONVERSION_AGENT_BACKEND=bedrock (plus AWS_REGION and standard AWS
credentials) to run against the corporate Bedrock account; anything else
uses the first-party API via ANTHROPIC_API_KEY or an `ant auth login`
profile. Model IDs carry the `anthropic.` prefix on Bedrock.
"""

from __future__ import annotations

import os

import anthropic

BASE_MODEL = "claude-opus-4-8"


def is_bedrock() -> bool:
    return os.environ.get("CONVERSION_AGENT_BACKEND", "").lower() == "bedrock"


def model_id() -> str:
    return f"anthropic.{BASE_MODEL}" if is_bedrock() else BASE_MODEL


def make_client():
    if is_bedrock():
        from anthropic import AnthropicBedrockMantle
        return AnthropicBedrockMantle(aws_region=os.environ.get("AWS_REGION", "us-east-1"))
    return anthropic.Anthropic()
