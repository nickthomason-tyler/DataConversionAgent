"""System prompt construction and the tool-runner loop."""

from __future__ import annotations

from . import backend
from .config import ProjectContext
from .tools import ALL_TOOLS, set_project

MAX_TOKENS = 16000

# Stable across every client and every turn — this block is cached.
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


def build_system(project: ProjectContext) -> list[dict]:
    project_block = (
        f"Current project context:\n"
        f"- Client: {project.project.get('client_name', project.name)}\n"
        f"- Legacy source: {project.project.get('source_system', 'unknown')}\n"
        f"- Phase: {project.project.get('phase', 'unknown')}\n"
        f"- Mapping status counts: {project.mapping_status_counts}\n"
        f"- In-scope entities: {project.project.get('in_scope_entities', [])}\n"
    )
    return [
        # Stable prefix first, with the cache breakpoint on it.
        {"type": "text", "text": CORE_PROMPT, "cache_control": {"type": "ephemeral"}},
        # Volatile per-project context after the breakpoint.
        {"type": "text", "text": project_block},
    ]


class ConversionAgent:
    def __init__(self, project: ProjectContext):
        self.client = backend.make_client()
        self.project = project
        self.system = build_system(project)
        self.history: list[dict] = []
        set_project(project)

    def ask(self, question: str) -> str:
        self.history.append({"role": "user", "content": question})
        runner = self.client.beta.messages.tool_runner(
            model=backend.model_id(),
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            system=self.system,
            tools=ALL_TOOLS,
            messages=self.history,
        )
        final = runner.until_done()
        answer = "".join(b.text for b in final.content if b.type == "text")
        # Keep history text-only: the final answer is self-contained, so
        # intermediate tool turns don't need to be replayed on later turns.
        self.history.append({"role": "assistant", "content": answer})
        return answer
