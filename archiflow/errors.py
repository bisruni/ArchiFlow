"""Application-specific exception types and error formatting helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

LogFn = Callable[[str], None]


class OperationCancelledError(RuntimeError):
    """Raised when an active operation is cancelled by user or system signal."""


class ValidationError(ValueError):
    """Raised when user-provided configuration or paths are invalid."""


class TransactionError(RuntimeError):
    """Raised when transaction journal operations cannot proceed safely."""


def build_error_message(
    operation: str,
    *,
    path: str | Path | None = None,
    error: BaseException | None = None,
    context: Mapping[str, object] | None = None,
) -> str:
    """Build deterministic error text with optional path/context/cause details."""
    details: list[str] = []
    if path is not None:
        details.append(f"path='{path}'")
    if context:
        for key in sorted(context):
            details.append(f"{key}={context[key]!r}")

    message = operation
    if details:
        message = f"{operation} ({', '.join(details)})"
    if error is not None:
        message = f"{message}: {error}"
    return message


def record_error(
    errors: list[str] | None,
    *,
    log: LogFn | None,
    operation: str,
    path: str | Path | None = None,
    error: BaseException | None = None,
    context: Mapping[str, object] | None = None,
) -> str:
    """Create a normalized error message, append to list, and emit to log."""
    message = build_error_message(
        operation,
        path=path,
        error=error,
        context=context,
    )
    if errors is not None:
        errors.append(message)
    if log is not None:
        log(message)
    return message


def log_error(
    log: LogFn | None,
    *,
    operation: str,
    path: str | Path | None = None,
    error: BaseException | None = None,
    context: Mapping[str, object] | None = None,
) -> str:
    """Create normalized error message and emit to log when callback exists."""
    return record_error(
        None,
        log=log,
        operation=operation,
        path=path,
        error=error,
        context=context,
    )
