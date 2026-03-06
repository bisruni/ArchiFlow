from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from archiflow.models import (
    OperationTransaction,
    TransactionAction,
    TransactionEntry,
    TransactionLifecycleStatus,
    TransactionStatus,
)
from archiflow.transaction_service import TransactionService


def test_transaction_service_undo_reverses_done_entries_and_skips_others(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()

    moved_source = source_root / "moved.txt"
    moved_dest = target_root / "archive" / "moved.txt"
    moved_dest.parent.mkdir(parents=True)
    moved_dest.write_text("moved", encoding="utf-8")

    copied_source = source_root / "copied.txt"
    copied_source.write_text("copy-src", encoding="utf-8")
    copied_dest = target_root / "copies" / "copied.txt"
    copied_dest.parent.mkdir(parents=True)
    copied_dest.write_text("copy-dst", encoding="utf-8")

    quarantine_source = source_root / "dup.txt"
    quarantine_dest = target_root / ".archiflow_quarantine" / "dup.txt"
    quarantine_dest.parent.mkdir(parents=True)
    quarantine_dest.write_text("dup", encoding="utf-8")

    pending_source = source_root / "pending.txt"
    pending_dest = target_root / "pending" / "pending.txt"

    transaction = OperationTransaction(
        transaction_id="tx-undo",
        created_at_utc=datetime.now(tz=timezone.utc),
        source_root=source_root,
        target_root=target_root,
        entries=[
            TransactionEntry(
                action=TransactionAction.MOVED,
                source_path=moved_source,
                destination_path=moved_dest,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.DONE,
            ),
            TransactionEntry(
                action=TransactionAction.COPIED,
                source_path=copied_source,
                destination_path=copied_dest,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.DONE,
            ),
            TransactionEntry(
                action=TransactionAction.QUARANTINED_DUPLICATE,
                source_path=quarantine_source,
                destination_path=quarantine_dest,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.DONE,
            ),
            TransactionEntry(
                action=TransactionAction.MOVED,
                source_path=pending_source,
                destination_path=pending_dest,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.PENDING,
                error_message="cancelled",
            ),
            TransactionEntry(
                action=TransactionAction.DELETED_DUPLICATE,
                source_path=source_root / "deleted.txt",
                destination_path=None,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.DONE,
                reversible=False,
            ),
        ],
    )

    service = TransactionService()
    tx_file = service.save_transaction(transaction)
    summary = service.undo_transaction(tx_file)

    assert summary.files_moved == 1
    assert summary.files_copied == 1
    assert summary.duplicates_quarantined == 1
    assert any("Deleted file cannot be restored" in item for item in summary.errors)

    assert moved_source.exists()
    assert not moved_dest.exists()
    assert not copied_dest.exists()
    assert quarantine_source.exists()
    assert not quarantine_dest.exists()


def test_transaction_service_recover_interrupted_transactions_rolls_back_and_marks_status(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()

    source_path = source_root / "dup.txt"
    destination_path = target_root / ".archiflow_quarantine" / "dup.txt"
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text("dup", encoding="utf-8")

    transaction = OperationTransaction(
        transaction_id="tx-interrupted",
        created_at_utc=datetime.now(tz=timezone.utc),
        source_root=source_root,
        target_root=target_root,
        lifecycle_status=TransactionLifecycleStatus.RUNNING,
        checkpoint_stage="dedupe",
        checkpoint_processed_files=1,
        checkpoint_total_files=3,
        checkpoint_message="Interrupted during duplicate processing.",
        entries=[
            TransactionEntry(
                action=TransactionAction.QUARANTINED_DUPLICATE,
                source_path=source_path,
                destination_path=destination_path,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.DONE,
            ),
            TransactionEntry(
                action=TransactionAction.QUARANTINED_DUPLICATE,
                source_path=source_root / "pending.txt",
                destination_path=target_root / ".archiflow_quarantine" / "pending.txt",
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.PENDING,
                error_message="cancelled",
            ),
        ],
    )

    service = TransactionService()
    tx_file = service.save_transaction(transaction)
    assert service.find_recoverable_transactions(target_root) == [tx_file]

    summary = service.recover_interrupted_transactions(target_root)

    assert summary.duplicates_quarantined == 1
    assert source_path.exists()
    assert not destination_path.exists()

    updated_tx = service.load(tx_file)
    assert updated_tx.lifecycle_status is TransactionLifecycleStatus.ROLLED_BACK
    assert updated_tx.checkpoint_stage == "undo_completed"
    assert service.find_recoverable_transactions(target_root) == []


def test_transaction_service_verify_rollback_reports_unresolved_state(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir()
    target_root.mkdir()

    moved_source = source_root / "missing-after-rollback.txt"
    moved_dest = target_root / "archive" / "missing-after-rollback.txt"
    copied_dest = target_root / "copies" / "still-there.txt"
    copied_dest.parent.mkdir(parents=True, exist_ok=True)
    copied_dest.write_text("copy", encoding="utf-8")

    transaction = OperationTransaction(
        transaction_id="tx-verify",
        created_at_utc=datetime.now(tz=timezone.utc),
        source_root=source_root,
        target_root=target_root,
        entries=[
            TransactionEntry(
                action=TransactionAction.MOVED,
                source_path=moved_source,
                destination_path=moved_dest,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.DONE,
            ),
            TransactionEntry(
                action=TransactionAction.COPIED,
                source_path=source_root / "copy-source.txt",
                destination_path=copied_dest,
                timestamp_utc=datetime.now(tz=timezone.utc),
                status=TransactionStatus.DONE,
            ),
        ],
    )

    service = TransactionService()
    tx_file = service.save_transaction(transaction)
    issues = service.verify_rollback(tx_file)

    assert any("source missing after rollback" in issue for issue in issues)
    assert any("copied destination still exists" in issue for issue in issues)
