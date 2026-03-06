from __future__ import annotations

import logging
from itertools import product
from pathlib import Path

import pytest

from archiflow import logger as logger_module
from archiflow.cli import build_parser, main, print_summary
from archiflow.models import OperationSummary
from archiflow.pipeline import RunResult


@pytest.fixture(autouse=True)
def isolate_logger(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCHIFLOW_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARCHIFLOW_CONFIG_FILE", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("ARCHIFLOW_PROFILE_PATH", str(tmp_path / "profiles.json"))
    logger_module.reset_logging_state()
    logging.getLogger(logger_module.LOGGER_NAME).handlers.clear()


APPLY_MATRIX = list(
    product(["copy", "move"], ["off", "quarantine", "delete"], ["group_only", "dedupe_only", "group_and_dedupe"])
)


@pytest.mark.parametrize(("mode", "dedupe", "scope"), APPLY_MATRIX)
def test_cli_parser_apply_matrix(mode: str, dedupe: str, scope: str) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "apply",
            "--source",
            "/tmp/source",
            "--target",
            "/tmp/target",
            "--mode",
            mode,
            "--dedupe",
            dedupe,
            "--scope",
            scope,
        ]
    )
    assert args.command == "apply"
    assert args.mode == mode
    assert args.dedupe == dedupe
    assert args.scope == scope


@pytest.mark.parametrize(
    ("dup_groups", "dup_files", "quarantined", "errors"),
    [(g, g + 1, g % 4, g % 3) for g in range(12)],
)
def test_cli_print_summary_matrix(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, dup_groups: int, dup_files: int, quarantined: int, errors: int
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    result = RunResult(
        source_path=source,
        target_path=target,
        summary=OperationSummary(
            total_files_scanned=dup_files + 10,
            total_bytes_scanned=1024,
            duplicate_group_count=dup_groups,
            duplicate_files_found=dup_files,
            duplicate_bytes_reclaimable=512,
            files_copied=1,
            files_moved=2,
            duplicates_quarantined=quarantined,
            duplicates_deleted=0,
            errors=["e"] * errors,
        ),
        duplicate_groups=[],
        similar_image_groups=[],
        transaction_id=None,
        transaction_file_path=None,
        auto_report_json_path=None,
        auto_report_csv_path=None,
    )

    print_summary(result)
    out = capsys.readouterr().out
    assert f"Duplicate groups: {dup_groups}" in out
    assert f"Duplicate files: {dup_files}" in out
    assert f"Quarantined: {quarantined}" in out
    assert f"Errors: {errors}" in out


@pytest.mark.parametrize("duplicate_files", [0, 1, 2, 3, 4, 5])
def test_cli_preview_exit_matrix(tmp_path: Path, duplicate_files: int) -> None:
    source = tmp_path / f"source_{duplicate_files}"
    source.mkdir()
    for index in range(duplicate_files + 1):
        content = "dup" if index < duplicate_files else f"u{index}"
        (source / f"f{index}.txt").write_text(content, encoding="utf-8")

    exit_code = main(["preview", "--source", str(source)])
    assert exit_code == 0
