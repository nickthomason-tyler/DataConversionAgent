import pytest

from conversion_agent.guidance.backends import run_with_retries


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

    with pytest.raises(PermissionError):
        run_with_retries(
            operation,
            retries=2,
            is_transient=lambda _: False,
            sleep=lambda _: None,
        )

    assert attempts == 1
