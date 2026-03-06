from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from archiflow.errors import OperationCancelledError
from archiflow.models import OperationStage, ScanFilterOptions
from archiflow.scanner import FileScanner


def test_scanner_skips_internal_directories(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "normal.txt").write_text("ok", encoding="utf-8")

    internal = source / ".archiflow"
    internal.mkdir()
    (internal / "state.json").write_text("{}", encoding="utf-8")

    quarantine = source / ".archiflow_quarantine"
    quarantine.mkdir()
    (quarantine / "q.txt").write_text("q", encoding="utf-8")

    legacy_quarantine = source / "duplicates_quarantine"
    legacy_quarantine.mkdir()
    (legacy_quarantine / "legacy.txt").write_text("legacy", encoding="utf-8")

    scanner = FileScanner()
    records = scanner.scan(source)
    paths = {item.full_path.name for item in records}

    assert paths == {"normal.txt"}


def test_scanner_applies_extension_filters_and_collects_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("a", encoding="utf-8")
    (source / "b.jpg").write_text("b", encoding="utf-8")

    skipped: list[str] = []
    scanner = FileScanner()
    records = scanner.scan(
        source,
        filter_options=ScanFilterOptions(include_extensions=[".txt"]),
        skipped_files=skipped,
    )

    assert len(records) == 1
    assert records[0].full_path.name == "a.txt"
    assert any(item.endswith("b.jpg") for item in skipped)


def test_scanner_cancellation_raises_operation_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for index in range(10):
        (source / f"f{index}.txt").write_text(str(index), encoding="utf-8")

    calls = 0

    def is_set() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    cancel_event = SimpleNamespace(is_set=is_set)
    scanner = FileScanner()

    with pytest.raises(OperationCancelledError):
        scanner.scan(source, cancel_event=cancel_event)  # type: ignore[arg-type]


def test_scanner_emits_progress_every_100_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for index in range(105):
        (source / f"f{index}.txt").write_text("x", encoding="utf-8")

    progress_events: list[tuple[OperationStage, int, str]] = []

    def progress(item) -> None:  # type: ignore[no-untyped-def]
        progress_events.append((item.stage, item.processed_files, item.message))

    scanner = FileScanner()
    records = scanner.scan(source, progress=progress)

    assert len(records) == 105
    assert any(stage is OperationStage.SCANNING and processed == 100 for stage, processed, _ in progress_events)


def test_scanner_scan_iter_returns_same_paths_as_scan(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for index in range(12):
        (source / f"f{index}.txt").write_text(str(index), encoding="utf-8")

    scanner = FileScanner()
    from_iter = list(scanner.scan_iter(source))
    from_scan = scanner.scan(source)

    assert {str(item.full_path) for item in from_iter} == {str(item.full_path) for item in from_scan}
    assert sum(item.size_bytes for item in from_iter) == sum(item.size_bytes for item in from_scan)
