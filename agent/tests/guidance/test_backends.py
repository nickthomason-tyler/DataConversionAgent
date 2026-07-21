import pytest

from conversion_agent.core.errors import BackendError
from conversion_agent.core.settings import AppSettings
from conversion_agent.guidance import backends
from conversion_agent.guidance.backends import AnthropicBackendFactory, run_with_retries


class TransientFailure(Exception):
    pass


def test_transient_backend_operation_gets_two_retries() -> None:
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientFailure("try again")
        return "ok"

    result = run_with_retries(
        operation,
        retries=2,
        is_transient=lambda exc: isinstance(exc, TransientFailure),
        sleep=lambda _: None,
    )

    assert result == "ok"
    assert attempts == 3


def test_nontransient_backend_operation_is_not_retried() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise PermissionError("denied")

    with pytest.raises(BackendError, match="backend operation failed") as raised:
        run_with_retries(
            operation,
            retries=2,
            is_transient=lambda _: False,
            sleep=lambda _: None,
        )

    assert attempts == 1
    assert isinstance(raised.value.__cause__, PermissionError)
    assert "denied" not in str(raised.value)


def test_exhausted_transient_backend_failure_is_typed_after_retries() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise TransientFailure("still unavailable")

    with pytest.raises(BackendError, match="after 3 attempts") as raised:
        run_with_retries(
            operation,
            retries=2,
            is_transient=lambda exc: isinstance(exc, TransientFailure),
            sleep=lambda _: None,
        )

    assert attempts == 3
    assert isinstance(raised.value.__cause__, TransientFailure)


def test_backend_factory_construction_failure_is_typed(monkeypatch, tmp_path) -> None:
    def fail_to_construct():
        raise RuntimeError("credentials unavailable")

    monkeypatch.setattr(backends.anthropic, "Anthropic", fail_to_construct)
    factory = AnthropicBackendFactory(AppSettings(projects_root=tmp_path))

    with pytest.raises(BackendError, match="Could not create anthropic backend") as raised:
        factory.create()

    assert isinstance(raised.value.__cause__, RuntimeError)
