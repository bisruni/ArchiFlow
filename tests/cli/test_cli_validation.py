from __future__ import annotations

import logging
from pathlib import Path

import pytest

from archiflow import logger as logger_module
from archiflow.cli import main


@pytest.fixture(autouse=True)
def isolate_logger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCHIFLOW_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARCHIFLOW_CONFIG_FILE", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("ARCHIFLOW_PROFILE_PATH", str(tmp_path / "profiles.json"))
    logger_module.reset_logging_state()
    logging.getLogger(logger_module.LOGGER_NAME).handlers.clear()


def test_cli_scan_fails_for_missing_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing-source"
    exit_code = main(["scan", "--source", str(missing)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Kaynak klasör bulunamadı" in captured.err


def test_cli_apply_requires_target_for_group_scope(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("x", encoding="utf-8")

    exit_code = main(["apply", "--source", str(source), "--scope", "group_only"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Gruplama için hedef klasör seçmek zorunlu." in captured.err


def test_cli_apply_rejects_nested_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.txt").write_text("x", encoding="utf-8")
    nested_target = source / "nested-target"
    nested_target.mkdir()

    exit_code = main(
        [
            "apply",
            "--source",
            str(source),
            "--target",
            str(nested_target),
            "--scope",
            "group_only",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Hedef klasör kaynak klasörün içinde olamaz." in captured.err
