from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from archiflow.duplicate_detector import DuplicateDetector
from archiflow.models import (
    DedupeMode,
    OperationSummary,
    OperationTransaction,
    OrganizationMode,
    TransactionAction,
    TransactionStatus,
)
from archiflow.organizer import FileOrganizer
from archiflow.pause_controller import PauseController
from archiflow.scanner import FileScanner
from archiflow.transaction_service import TransactionService


def test_organizer_quarantine_flow_writes_transaction(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    (source / "a.txt").write_text("dup", encoding="utf-8")
    (source / "b.txt").write_text("dup", encoding="utf-8")
    (source / "c.txt").write_text("unique", encoding="utf-8")

    files = FileScanner().scan(source)
    duplicate_groups, _similar = DuplicateDetector().find_duplicates(
        files,
        cache=None,
        detect_similar_images=False,
        similar_max_distance=8,
        log=None,
        progress=None,
        cancel_event=threading.Event(),
        pause_controller=PauseController(),
    )

    organizer = FileOrganizer()
    summary = OperationSummary()
    tx_service = TransactionService()
    transaction = OperationTransaction(
        transaction_id="tx-organizer-quarantine",
        created_at_utc=datetime.now(tz=timezone.utc),
        source_root=source,
        target_root=target,
        entries=[],
    )
    tx_path = tx_service.save_transaction(transaction)

    removed = organizer.process_duplicates(
        duplicate_groups,
        dedupe_mode=DedupeMode.QUARANTINE,
        protected_paths=None,
        source_root=source,
        target_root=target,
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

    assert len(removed) == 1
    assert summary.duplicates_quarantined == 1
    assert not removed[0].full_path.exists()

    quarantined_files = list((target / ".archiflow_quarantine").rglob("*.txt"))
    assert len(quarantined_files) == 1

    saved_transaction = tx_service.load(tx_path)
    assert len(saved_transaction.entries) == 1
    assert saved_transaction.entries[0].action is TransactionAction.QUARANTINED_DUPLICATE
    assert saved_transaction.entries[0].status is TransactionStatus.DONE


def test_organizer_copy_handles_filename_collisions(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "one").mkdir(parents=True)
    (source / "two").mkdir(parents=True)
    target.mkdir()

    (source / "one" / "report.txt").write_text("first", encoding="utf-8")
    (source / "two" / "report.txt").write_text("second", encoding="utf-8")

    files = FileScanner().scan(source)

    organizer = FileOrganizer()
    summary = OperationSummary()
    tx_service = TransactionService()
    transaction = OperationTransaction(
        transaction_id="tx-organizer-copy",
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
        mode=OrganizationMode.COPY,
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

    copied_files = list((target / "Documents").rglob("report*.txt"))
    copied_names = sorted(item.name for item in copied_files)

    assert summary.files_copied == 2
    assert copied_names == ["report (1).txt", "report.txt"]

    saved_transaction = tx_service.load(tx_path)
    assert len(saved_transaction.entries) == 2
    assert all(entry.action is TransactionAction.COPIED for entry in saved_transaction.entries)
    assert all(entry.status is TransactionStatus.DONE for entry in saved_transaction.entries)
