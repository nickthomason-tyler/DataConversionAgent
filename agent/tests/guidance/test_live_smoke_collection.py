"""Ensure explicitly opt-in live smoke tests remain discoverable offline."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_live_smoke_tests_collect_without_credentials() -> None:
    agent_root = Path(__file__).parents[2]
    environment = {
        **os.environ,
        "ANTHROPIC_API_KEY": "",
        "AWS_ACCESS_KEY_ID": "",
        "AWS_PROFILE": "",
        "CONVERSION_AGENT_LIVE_BEDROCK": "",
    }
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "live"],
        cwd=agent_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_live_anthropic_guidance_service_smoke" in result.stdout
    assert "test_live_bedrock_guidance_service_smoke" in result.stdout
