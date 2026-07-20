from types import SimpleNamespace

import anthropic
import httpx
import pytest

from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance.session import GuidanceSession
from conversion_agent.projects.filesystem import FilesystemProjectRepository


class FakeRunner:
    def __init__(self, outcome):
        self.outcome = outcome
        self.until_done_calls = 0

    def until_done(self):
        self.until_done_calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeToolRunnerClient:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.runners: list[FakeRunner] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(tool_runner=self.tool_runner))

    def tool_runner(self, **_kwargs):
        runner = FakeRunner(next(self.outcomes))
        self.runners.append(runner)
        return runner


def transient_failure() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(
        message="offline transient failure",
        request=httpx.Request("POST", "https://example.test/messages"),
    )


def final_answer(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def make_session(project_root, client, *, retries: int, max_history_messages: int = 4):
    project = FilesystemProjectRepository(project_root).load("alpha")
    settings = AppSettings(
        projects_root=project_root,
        backend_retries=retries,
        max_history_messages=max_history_messages,
    )
    return GuidanceSession(
        project=project,
        client=client,
        model_id="fake-model",
        tools=SimpleNamespace(anthropic_tools=()),
        settings=settings,
        system=[],
    )


def test_ask_rebuilds_tool_runner_for_a_transient_retry(project_root) -> None:
    client = FakeToolRunnerClient([transient_failure(), final_answer("recovered")])
    session = make_session(project_root, client, retries=1)

    assert session.ask("retry this") == "recovered"
    assert len(client.runners) == 2
    assert [runner.until_done_calls for runner in client.runners] == [1, 1]


def test_failed_ask_restores_history_before_a_later_success(project_root) -> None:
    client = FakeToolRunnerClient([transient_failure(), final_answer("answered")])
    session = make_session(project_root, client, retries=0, max_history_messages=2)

    with pytest.raises(anthropic.APIConnectionError):
        session.ask("will fail")

    assert session.ask("will succeed") == "answered"
    assert session.history == [
        {"role": "user", "content": "will succeed"},
        {"role": "assistant", "content": "answered"},
    ]
    assert len(session.history) <= session.settings.max_history_messages
