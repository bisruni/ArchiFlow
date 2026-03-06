from __future__ import annotations

import logging
from pathlib import Path

import pytest

from archiflow import logger as logger_module


@pytest.fixture(autouse=True)
def isolate_logger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Reset logger singleton state for deterministic CLI/E2E tests."""
    monkeypatch.setenv("ARCHIFLOW_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARCHIFLOW_CONFIG_FILE", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("ARCHIFLOW_PROFILE_PATH", str(tmp_path / "profiles.json"))
    logger_module.reset_logging_state()
    logging.getLogger(logger_module.LOGGER_NAME).handlers.clear()


@pytest.fixture
def sample_fs_builder(tmp_path: Path):
    """Create reproducible sample source trees used across E2E scenarios."""

    def _build(*, duplicate_count: int, with_hidden: bool = True) -> tuple[Path, Path]:
        source = tmp_path / f"source_{duplicate_count}_{int(with_hidden)}"
        target = tmp_path / f"target_{duplicate_count}_{int(with_hidden)}"
        source.mkdir(parents=True)
        target.mkdir(parents=True)

        docs = source / "docs"
        images = source / "images"
        nested = source / "nested" / "deep"
        docs.mkdir(parents=True)
        images.mkdir(parents=True)
        nested.mkdir(parents=True)

        (docs / "report.txt").write_text("report", encoding="utf-8")
        (images / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (nested / "notes.md").write_text("notes", encoding="utf-8")

        for index in range(duplicate_count):
            (docs / f"dup_{index}.txt").write_text("dup-content", encoding="utf-8")

        if with_hidden:
            (source / ".hidden.txt").write_text("hidden", encoding="utf-8")

        return source, target

    return _build
