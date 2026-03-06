"""Central logging configuration and helpers for ArchiFlow."""

from __future__ import annotations

import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any

from .constants import LOGS_DIRNAME, app_state_dir

LOGGER_NAME = "archiflow"
DEFAULT_LOG_FILE_NAME = "archiflow.log"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5

_CONFIG_LOCK = Lock()


class KeyValueFormatter(logging.Formatter):
    """Serialize log records as compact key=value structured lines."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record into deterministic key=value structure."""
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        message = record.getMessage().replace("\n", "\\n")
        parts = [
            f"ts={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"module={record.module}",
            f"line={record.lineno}",
            f"msg={message!r}",
        ]
        transaction_id = getattr(record, "transaction_id", None)
        if transaction_id:
            parts.append(f"transaction_id={transaction_id}")
        return " ".join(parts)


def _parse_level(value: str | None) -> int:
    """Resolve textual log level to numeric logging level."""
    if not value:
        return logging.INFO
    resolved = logging.getLevelName(value.upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def _resolve_log_dir(log_dir: Path | None) -> Path:
    """Resolve effective log directory using env override and defaults."""
    env_dir = os.environ.get("ARCHIFLOW_LOG_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    if log_dir is not None:
        return log_dir.expanduser().resolve()
    return (app_state_dir(Path.cwd()) / LOGS_DIRNAME).resolve()


def configure_logging(
    *,
    log_dir: Path | None = None,
    level: str | None = None,
    force: bool = False,
) -> Path:
    """Configure root ArchiFlow logger and return active log file path."""
    with _CONFIG_LOCK:
        logger = logging.getLogger(LOGGER_NAME)
        active_log_file = _active_log_file_from_logger(logger)
        if not force and _is_logger_configured(logger) and active_log_file is not None:
            return active_log_file

        configured_level = _parse_level(level or os.environ.get("ARCHIFLOW_LOG_LEVEL"))
        console_level = _parse_level(os.environ.get("ARCHIFLOW_CONSOLE_LOG_LEVEL", "WARNING"))
        resolved_log_dir = _resolve_log_dir(log_dir)
        try:
            resolved_log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Last-resort fallback: temp directory should always be writable.
            resolved_log_dir = (Path(tempfile.gettempdir()) / "archiflow-logs").resolve()
            resolved_log_dir.mkdir(parents=True, exist_ok=True)
        log_file_path = resolved_log_dir / DEFAULT_LOG_FILE_NAME

        _close_and_clear_handlers(logger)
        logger.setLevel(configured_level)
        logger.propagate = False

        formatter = KeyValueFormatter()

        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(
            filename=log_file_path,
            maxBytes=DEFAULT_MAX_BYTES,
            backupCount=DEFAULT_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(configured_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info("Logging configured", extra={"transaction_id": ""})
        return log_file_path


def get_logger(name: str | None = None) -> logging.Logger:
    """Return configured project logger or a named child logger."""
    base_logger = logging.getLogger(LOGGER_NAME)
    if not _is_logger_configured(base_logger):
        configure_logging()
    if not name:
        return base_logger
    if name.startswith(LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def get_active_log_file() -> Path | None:
    """Return currently active rotating log file path if configured."""
    return _active_log_file_from_logger(logging.getLogger(LOGGER_NAME))


def reset_logging_state() -> None:
    """Reset logger handlers for test/process isolation."""
    with _CONFIG_LOCK:
        _close_and_clear_handlers(logging.getLogger(LOGGER_NAME))


def _active_log_file_from_logger(logger: logging.Logger) -> Path | None:
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            base_filename = getattr(handler, "baseFilename", "")
            if base_filename:
                return Path(base_filename).resolve()
    return None


def _is_logger_configured(logger: logging.Logger) -> bool:
    has_console = False
    has_file = False
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            has_file = True
        elif isinstance(handler, logging.StreamHandler):
            has_console = True
    return has_console and has_file


def _close_and_clear_handlers(logger: logging.Logger) -> None:
    handlers = list(logger.handlers)
    for handler in handlers:
        try:
            handler.flush()
        except Exception:
            pass
        try:
            handler.close()
        except Exception:
            pass
    logger.handlers.clear()


def log_exception(logger: logging.Logger, message: str, **extra: Any) -> None:
    """Convenience helper to log full exception traceback with metadata."""
    logger.exception(message, extra=extra)
