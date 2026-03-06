from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from archiflow.errors import OperationCancelledError
from archiflow.models import (
    DedupeMode,
    DuplicateGroup,
    ExecutionScope,
    FileCategory,
    FileRecord,
    OrganizationMode,
    ScanFilterOptions,
    TransactionLifecycleStatus,
    TransactionStatus,
)
from archiflow.pause_controller import PauseController
from archiflow.pipeline import ArchiFlowEngine, RunOptions


def test_pipeline_preview_and_apply_quarantine_with_undo(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    (source / "a.txt").write_text("dup", encoding="utf-8")
    (source / "b.txt").write_text("dup", encoding="utf-8")
    (source / "c.txt").write_text("solo", encoding="utf-8")

    engine = ArchiFlowEngine()
    cancel_event = threading.Event()
    pause_controller = PauseController()

    preview = engine.run(
        RunOptions(
            source_path=source,
            target_path=None,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=DedupeMode.QUARANTINE,
            execution_scope=ExecutionScope.GROUP_AND_DEDUPE,
            dry_run=True,
            detect_similar_images=False,
            apply_changes=False,
            filter_options=ScanFilterOptions(),
        ),
        log=None,
        progress=None,
        cancel_event=cancel_event,
        pause_controller=pause_controller,
    )

    assert preview.summary.total_files_scanned == 3
    assert preview.summary.duplicate_group_count == 1
    assert preview.summary.duplicate_files_found == 1
    assert preview.summary.duplicates_quarantined == 0
    assert preview.auto_report_json_path is not None and preview.auto_report_json_path.exists()
    assert preview.auto_report_csv_path is not None and preview.auto_report_csv_path.exists()

    applied = engine.run(
        RunOptions(
            source_path=source,
            target_path=target,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=DedupeMode.QUARANTINE,
            execution_scope=ExecutionScope.DEDUPE_ONLY,
            dry_run=False,
            detect_similar_images=False,
            apply_changes=True,
            filter_options=ScanFilterOptions(),
        ),
        log=None,
        progress=None,
        cancel_event=cancel_event,
        pause_controller=pause_controller,
    )

    assert applied.summary.duplicates_quarantined == 1
    assert applied.transaction_file_path is not None and applied.transaction_file_path.exists()
    assert any((target / ".archiflow_quarantine").rglob("*.txt"))

    undo_summary = engine.transaction_service.undo_last_transaction(target)
    assert undo_summary.duplicates_quarantined == 1
    assert sorted(item.name for item in source.glob("*.txt")) == ["a.txt", "b.txt", "c.txt"]


def test_pipeline_cancelled_apply_persists_checkpoint_and_is_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    source_files: list[FileRecord] = []
    for index in range(4):
        file_path = source / f"dup_{index}.txt"
        file_path.write_text("dup", encoding="utf-8")
        source_files.append(
            FileRecord(
                full_path=file_path,
                extension=".txt",
                size_bytes=file_path.stat().st_size,
                last_write_utc=datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc),
                category=FileCategory.TEXT,
            )
        )

    duplicate_group = DuplicateGroup(
        sha256_hash="abc123",
        size_bytes=source_files[0].size_bytes,
        files=source_files,
    )

    engine = ArchiFlowEngine()
    cancel_event = threading.Event()

    def fake_scan(*_args, **_kwargs) -> list[FileRecord]:
        return list(source_files)

    def fake_find_duplicates(*_args, **_kwargs) -> tuple[list[DuplicateGroup], list]:
        return [duplicate_group], []

    monkeypatch.setattr(engine.scanner, "scan", fake_scan)
    monkeypatch.setattr(engine.detector, "find_duplicates", fake_find_duplicates)

    class CancelAfterTwoCalls:
        def __init__(self) -> None:
            self.calls = 0

        def wait_if_paused(self, event: threading.Event | None) -> None:
            self.calls += 1
            if self.calls == 2 and event is not None:
                event.set()

    pause_controller = CancelAfterTwoCalls()

    with pytest.raises(OperationCancelledError):
        engine.run(
            RunOptions(
                source_path=source,
                target_path=target,
                organization_mode=OrganizationMode.COPY,
                dedupe_mode=DedupeMode.QUARANTINE,
                execution_scope=ExecutionScope.DEDUPE_ONLY,
                dry_run=False,
                detect_similar_images=False,
                apply_changes=True,
                filter_options=ScanFilterOptions(),
            ),
            log=None,
            progress=None,
            cancel_event=cancel_event,
            pause_controller=pause_controller,  # type: ignore[arg-type]
        )

    tx_file = engine.transaction_service.find_latest_transaction_file(target)
    assert tx_file is not None and tx_file.exists()

    tx = engine.transaction_service.load(tx_file)
    assert tx.lifecycle_status is TransactionLifecycleStatus.CANCELLED
    assert tx.checkpoint_stage == "cancelled"
    assert any(entry.status is TransactionStatus.DONE for entry in tx.entries)
    assert tx_file in engine.transaction_service.find_recoverable_transactions(target)

    recovered = engine.transaction_service.recover_interrupted_transactions(target)
    assert recovered.duplicates_quarantined >= 1
    assert len(list(source.glob("dup_*.txt"))) == 4


def test_pipeline_group_only_apply_uses_streaming_scanner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    for index in range(5):
        (source / f"f_{index}.txt").write_text(f"data-{index}", encoding="utf-8")

    engine = ArchiFlowEngine()

    def fail_scan(*_args, **_kwargs) -> list[FileRecord]:
        raise AssertionError("scan() should not be called for group-only apply path")

    monkeypatch.setattr(engine.scanner, "scan", fail_scan)

    result = engine.run(
        RunOptions(
            source_path=source,
            target_path=target,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=DedupeMode.OFF,
            execution_scope=ExecutionScope.GROUP_ONLY,
            dry_run=True,
            detect_similar_images=False,
            apply_changes=True,
            filter_options=ScanFilterOptions(),
        ),
        log=None,
        progress=None,
        cancel_event=threading.Event(),
        pause_controller=PauseController(),
    )

    assert result.summary.total_files_scanned == 5
    assert result.summary.files_copied == 5
