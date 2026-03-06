from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from archiflow.duplicate_detector import DuplicateDetector
from archiflow.models import (
    DedupeMode,
    ExecutionScope,
    OperationSummary,
    OperationTransaction,
    OrganizationMode,
    ScanFilterOptions,
)
from archiflow.organizer import FileOrganizer
from archiflow.pause_controller import PauseController
from archiflow.pipeline import ArchiFlowEngine, RunOptions
from archiflow.scanner import FileScanner
from archiflow.transaction_service import TransactionService


@pytest.mark.parametrize("duplicate_count", list(range(2, 42)))
def test_integration_duplicate_detector_matrix(tmp_path: Path, duplicate_count: int) -> None:
    source = tmp_path / "source"
    source.mkdir()

    for index in range(duplicate_count):
        (source / f"dup_{index}.bin").write_bytes(b"x" * 1024)
    (source / "unique.bin").write_bytes(b"y" * 1024)

    files = FileScanner().scan(source)
    groups, similar = DuplicateDetector().find_duplicates(
        files,
        cache=None,
        detect_similar_images=False,
        similar_max_distance=8,
        log=None,
        progress=None,
        cancel_event=threading.Event(),
        pause_controller=PauseController(),
    )

    assert len(groups) == 1
    assert len(groups[0].files) == duplicate_count
    assert similar == []


@pytest.mark.parametrize("mode", [OrganizationMode.COPY, OrganizationMode.MOVE])
@pytest.mark.parametrize("file_count", list(range(1, 21)))
def test_integration_organizer_mode_matrix(tmp_path: Path, mode: OrganizationMode, file_count: int) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    for index in range(file_count):
        (source / f"f_{index}.txt").write_text(str(index), encoding="utf-8")

    files = FileScanner().scan(source)
    summary = OperationSummary()
    organizer = FileOrganizer()
    tx_service = TransactionService()
    transaction = OperationTransaction(
        transaction_id=f"tx-{mode.value}-{file_count}",
        created_at_utc=datetime.now(tz=timezone.utc),
        source_root=source,
        target_root=target,
        entries=[],
    )
    tx_path = tx_service.save_transaction(transaction)

    organizer.organize_by_category_and_date(
        files,
        total_files=len(files),
        target_root=target,
        mode=mode,
        dry_run=False,
        summary=summary,
        transaction=transaction,
        transaction_service=tx_service,
        transaction_file_path=tx_path,
        log=None,
        progress=None,
        cancel_event=threading.Event(),
        pause_controller=PauseController(),
    )
    organizer.finalize_transaction_journal(transaction, tx_service, tx_path)

    if mode is OrganizationMode.COPY:
        assert summary.files_copied == file_count
        assert len(list(source.glob("*.txt"))) == file_count
    else:
        assert summary.files_moved == file_count
        assert len(list(source.glob("*.txt"))) == 0

    copied = list((target / "Documents").rglob("*.txt"))
    assert len(copied) == file_count


@pytest.mark.parametrize(
    ("scope", "dedupe_mode"),
    [
        (ExecutionScope.GROUP_ONLY, DedupeMode.OFF),
        (ExecutionScope.DEDUPE_ONLY, DedupeMode.QUARANTINE),
        (ExecutionScope.GROUP_AND_DEDUPE, DedupeMode.QUARANTINE),
    ]
    * 5,
)
def test_integration_pipeline_scope_matrix(tmp_path: Path, scope: ExecutionScope, dedupe_mode: DedupeMode) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "a.txt").write_text("dup", encoding="utf-8")
    (source / "b.txt").write_text("dup", encoding="utf-8")
    (source / "c.txt").write_text("x", encoding="utf-8")

    engine = ArchiFlowEngine()
    result = engine.run(
        RunOptions(
            source_path=source,
            target_path=target if scope.includes_grouping else None,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=dedupe_mode,
            execution_scope=scope,
            dry_run=True,
            detect_similar_images=False,
            apply_changes=False,
            filter_options=ScanFilterOptions(),
        ),
        log=None,
        progress=None,
        cancel_event=threading.Event(),
        pause_controller=PauseController(),
    )

    assert result.summary.total_files_scanned == 3
    if scope.includes_dedupe:
        assert result.summary.duplicate_group_count >= 1
