from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, TYPE_CHECKING, Iterable

from .classifier import folder_name
from .errors import OperationCancelledError
from .models import (
    DedupeMode,
    DuplicateGroup,
    FileRecord,
    OperationProgress,
    OperationStage,
    OperationSummary,
    OperationTransaction,
    OrganizationMode,
    TransactionAction,
    TransactionEntry,
    TransactionStatus,
)

if TYPE_CHECKING:
    from .transaction_service import TransactionService

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


class FileOrganizer:
    def __init__(self) -> None:
        self._tx_flush_interval_seconds = 1.0
        self._tx_flush_update_threshold = 25
        self._tx_last_flush_monotonic = 0.0
        self._tx_updates_since_flush = 0
        self._tx_dirty = False
        self._tx_context_key: str | None = None

    def process_duplicates(
        self,
        duplicate_groups: list[DuplicateGroup],
        *,
        dedupe_mode: DedupeMode,
        protected_paths: set[str] | None,
        source_root: Path,
        target_root: Path,
        dry_run: bool,
        summary: OperationSummary,
        transaction: OperationTransaction | None,
        transaction_service: TransactionService | None,
        transaction_file_path: Path | None,
        log: LogFn | None,
        progress: ProgressFn | None,
        cancel_event: threading.Event | None,
        pause_controller=None,
    ) -> list[FileRecord]:
        if dedupe_mode is DedupeMode.OFF:
            return []

        # Helper: Normalize paths for comparison (Windows case-insensitive safe)
        def normalize_path_for_comparison(p: str | Path) -> Path:
            """Convert path to absolute resolved form for reliable comparison."""
            if isinstance(p, str):
                p = Path(p)
            return p.resolve()

        # Convert protected_paths to normalized resolved paths
        protected_paths_normalized = {
            normalize_path_for_comparison(p) for p in (protected_paths or set())
        }

        unique_remove: dict[str, FileRecord] = {}
        for group in duplicate_groups:
            if len(group.files) < 2:
                continue

            # Find which files should be kept (protected or first in group)
            keep_files_normalized = {
                normalize_path_for_comparison(item.full_path)
                for item in group.files
                if normalize_path_for_comparison(item.full_path) in protected_paths_normalized
            }

            if not keep_files_normalized:
                # If none protected, keep the first file
                keep_files_normalized = {normalize_path_for_comparison(group.files[0].full_path)}

            # Mark duplicates for removal (files not in keep set)
            for item in group.files:
                if normalize_path_for_comparison(item.full_path) in keep_files_normalized:
                    continue
                unique_remove[str(item.full_path)] = item

        to_remove = list(unique_remove.values())
        if not to_remove:
            return []

        quarantine_root = target_root / ".filegrouper_quarantine" / datetime.now().strftime("%Y%m%d_%H%M%S")

        for index, duplicate in enumerate(to_remove, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)
            tx_entry: TransactionEntry | None = None

            if not duplicate.full_path.exists():
                summary.skipped_files.append(str(duplicate.full_path))
                continue

            try:
                if dedupe_mode is DedupeMode.DELETE:
                    if not dry_run:
                        tx_entry = TransactionEntry(
                            action=TransactionAction.DELETED_DUPLICATE,
                            source_path=duplicate.full_path,
                            destination_path=None,
                            timestamp_utc=datetime.utcnow(),
                            status=TransactionStatus.PENDING,
                            reversible=False,  # Deleted files cannot be restored
                        )
                        self._append_transaction_entry(
                            transaction=transaction,
                            transaction_service=transaction_service,
                            transaction_file_path=transaction_file_path,
                            entry=tx_entry,
                        )
                    if not dry_run:
                        duplicate.full_path.unlink(missing_ok=True)
                    summary.duplicates_deleted += 1
                    if tx_entry is not None:
                        tx_entry.status = TransactionStatus.DONE
                        tx_entry.error_message = None
                        self._flush_transaction(transaction, transaction_service, transaction_file_path)
                else:
                    relative = safe_relative_path(duplicate.full_path, source_root)
                    destination = build_unique_path(quarantine_root / relative)
                    if not dry_run:
                        tx_entry = TransactionEntry(
                            action=TransactionAction.QUARANTINED_DUPLICATE,
                            source_path=duplicate.full_path,
                            destination_path=destination,
                            timestamp_utc=datetime.utcnow(),
                            status=TransactionStatus.PENDING,
                        )
                        self._append_transaction_entry(
                            transaction=transaction,
                            transaction_service=transaction_service,
                            transaction_file_path=transaction_file_path,
                            entry=tx_entry,
                        )

                    if not dry_run:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(duplicate.full_path), str(destination))

                    summary.duplicates_quarantined += 1
                    if tx_entry is not None:
                        tx_entry.status = TransactionStatus.DONE
                        tx_entry.error_message = None
                        self._flush_transaction(transaction, transaction_service, transaction_file_path)
            except (OSError, IOError, PermissionError) as exc:  # File operation failures
                if tx_entry is not None:
                    tx_entry.status = TransactionStatus.FAILED
                    tx_entry.error_message = str(exc)
                    self._flush_transaction(transaction, transaction_service, transaction_file_path)
                summary.errors.append(f"Could not process duplicate '{duplicate.full_path}': {exc}")
                if log:
                    log(f"Could not process duplicate '{duplicate.full_path}': {exc}")

            if progress and index % 50 == 0:
                progress(
                    OperationProgress(
                        stage=OperationStage.ORGANIZING,
                        processed_files=index,
                        total_files=len(to_remove),
                        message="Processing duplicates",
                    )
                )

        return to_remove

    def organize_by_category_and_date(
        self,
        files: Iterable[FileRecord],
        *,
        total_files: int | None,
        target_root: Path,
        mode: OrganizationMode,
        dry_run: bool,
        summary: OperationSummary,
        transaction: OperationTransaction | None,
        transaction_service: TransactionService | None,
        transaction_file_path: Path | None,
        log: LogFn | None,
        progress: ProgressFn | None,
        cancel_event: threading.Event | None,
        pause_controller=None,
    ) -> None:
        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)

        total = total_files or 0
        last_index = 0
        for index, file in enumerate(files, start=1):
            last_index = index
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)
            tx_entry: TransactionEntry | None = None

            if not file.full_path.exists():
                summary.skipped_files.append(str(file.full_path))
                continue

            local_time = file.last_write_utc.astimezone()
            destination_folder = target_root / folder_name(file.category) / f"{local_time.year:04d}" / f"{local_time.month:02d}"
            destination_path = build_unique_path(destination_folder / file.full_path.name)

            if dry_run:
                if mode is OrganizationMode.COPY:
                    summary.files_copied += 1
                else:
                    summary.files_moved += 1
                continue

            try:
                destination_folder.mkdir(parents=True, exist_ok=True)
                tx_action = TransactionAction.COPIED if mode is OrganizationMode.COPY else TransactionAction.MOVED
                tx_entry = TransactionEntry(
                    action=tx_action,
                    source_path=file.full_path,
                    destination_path=destination_path,
                    timestamp_utc=datetime.utcnow(),
                    status=TransactionStatus.PENDING,
                )
                self._append_transaction_entry(
                    transaction=transaction,
                    transaction_service=transaction_service,
                    transaction_file_path=transaction_file_path,
                    entry=tx_entry,
                )
                if mode is OrganizationMode.COPY:
                    shutil.copy2(file.full_path, destination_path)
                    summary.files_copied += 1
                else:
                    shutil.move(str(file.full_path), str(destination_path))
                    summary.files_moved += 1
                tx_entry.status = TransactionStatus.DONE
                tx_entry.error_message = None
                self._flush_transaction(transaction, transaction_service, transaction_file_path)
            except (OSError, IOError, PermissionError) as exc:  # File operation failures
                if tx_entry is not None:
                    tx_entry.status = TransactionStatus.FAILED
                    tx_entry.error_message = str(exc)
                    self._flush_transaction(transaction, transaction_service, transaction_file_path)
                summary.errors.append(f"Could not process '{file.full_path}': {exc}")
                if log:
                    log(f"Could not process '{file.full_path}': {exc}")

            if progress and index % 50 == 0:
                progress(
                    OperationProgress(
                        stage=OperationStage.ORGANIZING,
                        processed_files=index,
                        total_files=total,
                        message="Organizing files",
                    )
                )
        if progress and total > 0 and last_index % 50 != 0:
            progress(
                OperationProgress(
                    stage=OperationStage.ORGANIZING,
                    processed_files=last_index,
                    total_files=total,
                    message="Organizing files",
                )
            )

    def _append_transaction_entry(
        self,
        *,
        transaction: OperationTransaction | None,
        transaction_service: TransactionService | None,
        transaction_file_path: Path | None,
        entry: TransactionEntry,
    ) -> None:
        if transaction is None:
            return
        transaction.entries.append(entry)
        # Safety-critical: pending entry must hit disk before file mutation starts.
        self._flush_transaction(transaction, transaction_service, transaction_file_path, force=True)

    def _flush_transaction(
        self,
        transaction: OperationTransaction | None,
        transaction_service: TransactionService | None,
        transaction_file_path: Path | None,
        *,
        force: bool = False,
    ) -> None:
        if transaction is None or transaction_service is None or transaction_file_path is None:
            return

        key = str(transaction_file_path.resolve())
        if self._tx_context_key != key:
            self._tx_context_key = key
            self._tx_last_flush_monotonic = 0.0
            self._tx_updates_since_flush = 0
            self._tx_dirty = False

        self._tx_dirty = True
        self._tx_updates_since_flush += 1
        now = time.monotonic()
        if (
            not force
            and self._tx_updates_since_flush < self._tx_flush_update_threshold
            and (now - self._tx_last_flush_monotonic) < self._tx_flush_interval_seconds
        ):
            return

        transaction_service.save_transaction_to_path(transaction, transaction_file_path)
        self._tx_last_flush_monotonic = now
        self._tx_updates_since_flush = 0
        self._tx_dirty = False

    def finalize_transaction_journal(
        self,
        transaction: OperationTransaction | None,
        transaction_service: TransactionService | None,
        transaction_file_path: Path | None,
    ) -> None:
        self._flush_transaction(
            transaction,
            transaction_service,
            transaction_file_path,
            force=True,
        )


def safe_relative_path(path: Path, root: Path) -> Path:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return Path(path.name)

    if str(relative).startswith(".."):
        return Path(path.name)
    return relative


def build_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
