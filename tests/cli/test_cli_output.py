from __future__ import annotations

import logging
from pathlib import Path

import pytest

from archiflow import logger as logger_module
from archiflow.cli import main, print_summary
from archiflow.models import OperationSummary
from archiflow.pipeline import RunResult


@pytest.fixture(autouse=True)
def isolate_logger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCHIFLOW_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARCHIFLOW_CONFIG_FILE", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("ARCHIFLOW_PROFILE_PATH", str(tmp_path / "profiles.json"))
    logger_module.reset_logging_state()
    logging.getLogger(logger_module.LOGGER_NAME).handlers.clear()


def test_print_summary_includes_all_key_fields(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    result = RunResult(
        source_path=source,
        target_path=target,
        summary=OperationSummary(
            total_files_scanned=12,
            total_bytes_scanned=1200,
            duplicate_group_count=2,
            duplicate_files_found=3,
            duplicate_bytes_reclaimable=500,
            files_copied=4,
            files_moved=1,
            duplicates_quarantined=2,
            duplicates_deleted=0,
            errors=["err1"],
        ),
        duplicate_groups=[],
        similar_image_groups=[],
        transaction_id="tx1",
        transaction_file_path=None,
        auto_report_json_path=None,
        auto_report_csv_path=None,
    )

    print_summary(result)
    output = capsys.readouterr().out

    assert "== Summary ==" in output
    assert "Scanned files: 12" in output
    assert "Duplicate groups: 2" in output
    assert "Quarantined: 2" in output
    assert "Errors: 1" in output


def test_cli_scan_output_contains_summary_block(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "single.txt").write_text("only", encoding="utf-8")

    exit_code = main(["scan", "--source", str(source)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "== Summary ==" in output
    assert "Scanned files: 1" in output
