"""A conversation session bound to one immutable conversion project."""

from __future__ import annotations

from typing import Any

from conversion_agent.projects.models import ProjectContext

from .backends import run_with_retries

MAX_TOKENS = 16_000

CORE_PROMPT = """\
You are the Conversion Guidance Agent for our EPL (Energov / Permitting &
Licensing) implementation teams. You provide best practices, technical
guidance, and product expertise for migrating client legacy data into the
Data Conversion Template (DCT) and on to configured EPL databases.

Audience: internal implementation consultants and conversion analysts.

Rules:
- Ground every substantive claim in a tool result. Cite knowledge-base
  sources as [source: <file> § <heading>] and dictionary lookups as
  [DCT: <table>.<column>].
- If the tools do not support an answer, say "I don't know — flagging for
  the Conversion Lead" rather than guessing. Never invent DCT fields,
  valid values, or EPL configuration behavior.
- You are read-only: recommend mapping or workbook changes as drafts for a
  consultant to apply; never claim to have changed anything.
- Keep answers practical and specific to this client's project context.
"""


def build_system(project: ProjectContext) -> list[dict[str, Any]]:
    metadata = project.metadata
    project_block = (
        "Current project context:\n"
        f"- Client: {metadata.client_name}\n"
        f"- Legacy source: {metadata.source_system}\n"
        f"- Phase: {metadata.phase}\n"
        f"- Mapping status counts: {project.mapping_status_counts}\n"
        f"- In-scope entities: {list(metadata.in_scope_entities)}\n"
    )
    return [
        {"type": "text", "text": CORE_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": project_block},
    ]


class GuidanceSession:
    def __init__(self, *, project, client, model_id, tools, settings, system):
        self.project = project
        self.client = client
        self.model_id = model_id
        self.tools = tools
        self.settings = settings
        self.system = system
        self.history: list[dict[str, Any]] = []

    def _trim_history(self) -> None:
        while len(self.history) > self.settings.max_history_messages:
            del self.history[:2]

    def ask(self, question: str) -> str:
        self.history.append({"role": "user", "content": question})
        self._trim_history()
        runner = self.client.beta.messages.tool_runner(
            model=self.model_id,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=self.system,
            tools=self.tools.anthropic_tools,
            messages=self.history,
        )
        final = run_with_retries(runner.until_done, retries=self.settings.backend_retries)
        answer = "".join(block.text for block in final.content if block.type == "text")
        self.history.append({"role": "assistant", "content": answer})
        self._trim_history()
        return answer

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        return self.tools.call(name, arguments)
