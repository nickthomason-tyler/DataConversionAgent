"""Shared command-line error handling."""

from __future__ import annotations

import sys
import traceback

from conversion_agent.core.errors import ConversionAgentError


def render_error(error: Exception, *, debug: bool = False) -> int:
    """Write a stable user-facing error and return its process exit code."""
    if debug:
        traceback.print_exception(error)
    else:
        print(f"error: {error}", file=sys.stderr)
    return error.exit_code if isinstance(error, ConversionAgentError) else 1
