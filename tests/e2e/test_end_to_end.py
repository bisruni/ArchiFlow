from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import pytest

from archiflow.cli import main

WORKFLOW_MATRIX = list(
    product(
        ["group_only", "dedupe_only", "group_and_dedupe"],
        ["copy", "move"],
        ["off", "quarantine"],
        [False, True],
    )
)


@pytest.mark.parametrize(("scope", "mode", "dedupe", "dry_run"), WORKFLOW_MATRIX)
def test_e2e_complete_workflow_matrix(
    sample_fs_builder,
    scope: str,
    mode: str,
    dedupe: str,
    dry_run: bool,
) -> None:
    """Complete workflows: apply command succeeds for all supported mode combinations."""
    source, target = sample_fs_builder(duplicate_count=2, with_hidden=False)

    args = [
        "apply",
        "--source",
        str(source),
        "--target",
        str(target),
        "--scope",
        scope,
        "--mode",
        mode,
        "--dedupe",
        dedupe,
    ]
    if dry_run:
        args.append("--dry-run")

    exit_code = main(args)
    assert exit_code == 0

    report_source = source / "docs" / "report.txt"
    includes_grouping = scope != "dedupe_only"
    includes_dedupe = scope != "group_only"

    if includes_grouping and mode == "move" and not dry_run:
        assert not report_source.exists()
    else:
        assert report_source.exists()

    if includes_grouping and not dry_run:
        assert any((target / "Documents").rglob("*.txt"))

    if includes_dedupe and dedupe == "quarantine" and not dry_run:
        quarantine_base = source if scope == "dedupe_only" else target
        assert any((quarantine_base / ".archiflow_quarantine").rglob("*.txt"))


@pytest.mark.parametrize("duplicate_count", list(range(0, 10)))
def test_e2e_edge_case_preview_duplicate_counts(sample_fs_builder, tmp_path: Path, duplicate_count: int) -> None:
    """Edge cases: preview handles varying duplicate counts and hidden files correctly."""
    source, _target = sample_fs_builder(duplicate_count=duplicate_count, with_hidden=True)
    report = tmp_path / f"preview_{duplicate_count}.json"

    exit_code = main(["preview", "--source", str(source), "--report", str(report)])
    assert exit_code == 0
    assert report.exists()

    payload = json.loads(report.read_text(encoding="utf-8"))
    summary = payload["summary"]

    expected_total_scanned = 3 + duplicate_count  # hidden file is excluded by default
    expected_dupe_files = max(0, duplicate_count - 1)
    expected_dupe_groups = 1 if duplicate_count >= 2 else 0

    assert summary["total_files_scanned"] == expected_total_scanned
    assert summary["duplicate_files_found"] == expected_dupe_files
    assert summary["duplicate_group_count"] == expected_dupe_groups


def test_e2e_error_missing_source_scan(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Error scenario: scan returns validation error for missing source path."""
    missing = tmp_path / "missing_scan"
    exit_code = main(["scan", "--source", str(missing)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Kaynak klasör bulunamadı" in captured.err


def test_e2e_error_missing_source_preview(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Error scenario: preview returns validation error for missing source path."""
    missing = tmp_path / "missing_preview"
    exit_code = main(["preview", "--source", str(missing)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Kaynak klasör bulunamadı" in captured.err


def test_e2e_error_source_not_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Error scenario: apply rejects source values that are not directories."""
    source_file = tmp_path / "source.txt"
    source_file.write_text("x", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()

    exit_code = main(["apply", "--source", str(source_file), "--target", str(target), "--scope", "group_only"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Kaynak bir klasör olmalı" in captured.err


def test_e2e_error_missing_target_for_group_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Error scenario: apply group-only requires target path."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "f.txt").write_text("x", encoding="utf-8")

    exit_code = main(["apply", "--source", str(source), "--scope", "group_only"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Gruplama için hedef klasör seçmek zorunlu." in captured.err


def test_e2e_error_source_equals_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Error scenario: source and target cannot be identical."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "f.txt").write_text("x", encoding="utf-8")

    exit_code = main(
        [
            "apply",
            "--source",
            str(source),
            "--target",
            str(source),
            "--scope",
            "group_only",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Kaynak ve hedef klasör aynı olamaz." in captured.err


def test_e2e_error_nested_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Error scenario: target cannot be nested under source."""
    source = tmp_path / "source"
    nested_target = source / "nested_target"
    source.mkdir()
    nested_target.mkdir()
    (source / "f.txt").write_text("x", encoding="utf-8")

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
