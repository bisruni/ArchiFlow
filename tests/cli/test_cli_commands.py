from __future__ import annotations

import json
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


def test_cli_scan_command_writes_report(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.txt").write_text("hello", encoding="utf-8")

    report = tmp_path / "scan-report.json"
    exit_code = main(["scan", "--source", str(source), "--report", str(report)])

    assert exit_code == 0
    assert report.exists()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["summary"]["total_files_scanned"] == 1
    assert payload["summary"]["duplicate_group_count"] == 0


def test_cli_preview_command_reports_duplicates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("dup", encoding="utf-8")
    (source / "b.txt").write_text("dup", encoding="utf-8")
    (source / "c.txt").write_text("other", encoding="utf-8")

    exit_code = main(["preview", "--source", str(source)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Duplicate groups: 1" in captured.out
    assert "Duplicate files: 1" in captured.out


def test_cli_apply_group_only_copy_copies_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "doc.txt").write_text("content", encoding="utf-8")
    target = tmp_path / "target"

    exit_code = main(
        [
            "apply",
            "--source",
            str(source),
            "--target",
            str(target),
            "--scope",
            "group_only",
            "--mode",
            "copy",
        ]
    )

    assert exit_code == 0
    copied_files = list(target.rglob("doc.txt"))
    assert len(copied_files) == 1
    assert (source / "doc.txt").exists()
