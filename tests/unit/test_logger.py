from __future__ import annotations

import logging
from pathlib import Path

import pytest

from archiflow import logger as logger_module
from archiflow.logger import LOGGER_NAME, configure_logging, get_active_log_file, get_logger


@pytest.fixture(autouse=True)
def isolate_logger_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCHIFLOW_LOG_DIR", str(tmp_path / "logs"))
    logger_module.reset_logging_state()


def test_configure_logging_is_idempotent_without_global_mutable_flags() -> None:
    first = configure_logging()
    second = configure_logging()

    root_logger = logging.getLogger(LOGGER_NAME)
    assert first == second
    assert len(root_logger.handlers) == 2
    assert get_active_log_file() == first


def test_configure_logging_force_reconfigures_target_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCHIFLOW_LOG_DIR", raising=False)
    dir1 = tmp_path / "logs-1"
    dir2 = tmp_path / "logs-2"

    first = configure_logging(log_dir=dir1, force=True)
    second = configure_logging(log_dir=dir2, force=True)

    assert first.parent == dir1.resolve()
    assert second.parent == dir2.resolve()
    assert get_active_log_file() == second


def test_reset_logging_state_clears_handlers() -> None:
    configure_logging()
    assert logging.getLogger(LOGGER_NAME).handlers

    logger_module.reset_logging_state()

    assert logging.getLogger(LOGGER_NAME).handlers == []
    assert get_active_log_file() is None


def test_child_logger_uses_same_isolated_root_configuration() -> None:
    configure_logging()
    root_logger = logging.getLogger(LOGGER_NAME)
    handler_count = len(root_logger.handlers)

    child = get_logger("cli")
    assert child.name == f"{LOGGER_NAME}.cli"
    assert len(root_logger.handlers) == handler_count
