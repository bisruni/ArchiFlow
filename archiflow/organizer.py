"""File organization and duplicate action execution with transaction journaling."""

from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

from .classifier import folder_name
from .constants import (
    DUPLICATE_PROGRESS_EVERY,
    ORGANIZE_PROGRESS_EVERY,
    TX_FLUSH_INTERVAL_SECONDS,
    TX_FLUSH_UPDATE_THRESHOLD,
    quarantine_dir,
)
from .errors import OperationCancelledError, record_error
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
    TransactionLifecycleStatus,
    TransactionStatus,
)

if TYPE_CHECKING:
    from .pause_controller import PauseController
    from .transaction_service import TransactionService

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


class FileOrganizer:
    """Apply duplicate handling and category/date-based organization."""

    def __init__(self) -> None:
        """Initialize transaction flush rate-limit tracking state."""
        self._tx_flush_interval_seconds = TX_FLUSH_INTERVAL_SECONDS
        self._tx_flush_update_threshold = TX_FLUSH_UPDATE_THRESHOLD
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
        pause_controller: PauseController | None = None,
    ) -> list[FileRecord]:
        """Execute dedupe action for duplicates and return touched file records."""
        if dedupe_mode is DedupeMode.OFF:
            return []

        case_insensitive_fs = os.name == "nt"
        resolve_cache: dict[Path, str] = {}

        def normalize_path_for_comparison(p: str | Path) -> str:
            if isinstance(p, str):
                p = Path(p)
            if p in resolve_cache:
                return resolve_cache[p]
            try:
                normalized = str(p.resolve())
            except OSError:
                normalized = str(p.absolute())
            if case_insensitive_fs:
                normalized = normalized.casefold()
            resolve_cache[p] = normalized
            return normalized

        protected_paths_normalized = {normalize_path_for_comparison(p) for p in (protected_paths or set())}

        unique_remove: dict[str, FileRecord] = {}
        for group in duplicate_groups:
            if len(group.files) < 2:
                continue

            normalized_group = [(normalize_path_for_comparison(item.full_path), item) for item in group.files]
            keep_files_normalized = {
                normalized_key
                for normalized_key, _item in normalized_group
                if normalized_key in protected_paths_normalized
            }

            if not keep_files_normalized and normalized_group:
                keep_files_normalized = {normalized_group[0][0]}

            for normalized_key, item in normalized_group:
                if normalized_key in keep_files_normalized:
                    continue
                unique_remove[normalized_key] = item

        to_remove = list(unique_remove.values())
        if not to_remove:
            self._update_transaction_checkpoint(
                transaction=transaction,
                transaction_service=transaction_service,
                transaction_file_path=transaction_file_path,
                stage="dedupe",
                processed_files=0,
                total_files=0,
                message="No duplicates to process.",
            )
            return []

        quarantine_root = quarantine_dir(target_root) / datetime.now().strftime("%Y%m%d_%H%M%S")
        self._update_transaction_checkpoint(
            transaction=transaction,
            transaction_service=transaction_service,
            transaction_file_path=transaction_file_path,
            stage="dedupe",
            processed_files=0,
            total_files=len(to_remove),
            message="Duplicate processing started.",
            force=True,
        )

        for index, duplicate in enumerate(to_remove, start=1):
            if cancel_event is not None and cancel_event.is_set():
                self._update_transaction_checkpoint(
                    transaction=transaction,
                    transaction_service=transaction_service,
                    transaction_file_path=transaction_file_path,
                    stage="dedupe",
                    processed_files=index - 1,
                    total_files=len(to_remove),
                    message="Duplicate processing cancelled.",
                    force=True,
                )
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
                            timestamp_utc=datetime.now(timezone.utc),
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
                            timestamp_utc=datetime.now(timezone.utc),
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
                record_error(
                    summary.errors,
                    log=log,
                    operation="Could not process duplicate",
                    path=duplicate.full_path,
                    error=exc,
                    context={"dedupe_mode": dedupe_mode.value},
                )

            if progress and index % DUPLICATE_PROGRESS_EVERY == 0:
                progress(
                    OperationProgress(
                        stage=OperationStage.ORGANIZING,
                        processed_files=index,
                        total_files=len(to_remove),
                        message="Processing duplicates",
                    )
                )
            self._update_transaction_checkpoint(
                transaction=transaction,
                transaction_service=transaction_service,
                transaction_file_path=transaction_file_path,
                stage="dedupe",
                processed_files=index,
                total_files=len(to_remove),
                message="Duplicate processing in progress.",
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
        pause_controller: PauseController | None = None,
    ) -> None:
        """Organize non-skipped files into target category/year/month tree."""
        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)

        total = total_files if total_files is not None else 0
        last_index = 0
        self._update_transaction_checkpoint(
            transaction=transaction,
            transaction_service=transaction_service,
            transaction_file_path=transaction_file_path,
            stage="organize",
            processed_files=0,
            total_files=total,
            message="Organization started.",
            force=True,
        )
        for index, file in enumerate(files, start=1):
            last_index = index
            if cancel_event is not None and cancel_event.is_set():
                self._update_transaction_checkpoint(
                    transaction=transaction,
                    transaction_service=transaction_service,
                    transaction_file_path=transaction_file_path,
                    stage="organize",
                    processed_files=index - 1,
                    total_files=total,
                    message="Organization cancelled.",
                    force=True,
                )
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)
            tx_entry: TransactionEntry | None = None

            if not file.full_path.exists():
                summary.skipped_files.append(str(file.full_path))
                continue

            local_time = file.last_write_utc.astimezone()
            destination_folder = (
                target_root / folder_name(file.category) / f"{local_time.year:04d}" / f"{local_time.month:02d}"
            )
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
                    timestamp_utc=datetime.now(timezone.utc),
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
                record_error(
                    summary.errors,
                    log=log,
                    operation="Could not process file operation",
                    path=file.full_path,
                    error=exc,
                    context={"mode": mode.value},
                )

            if progress and index % ORGANIZE_PROGRESS_EVERY == 0:
                progress_total = total if total > 0 else index
                progress(
                    OperationProgress(
                        stage=OperationStage.ORGANIZING,
                        processed_files=index,
                        total_files=progress_total,
                        message="Organizing files",
                    )
                )
            self._update_transaction_checkpoint(
                transaction=transaction,
                transaction_service=transaction_service,
                transaction_file_path=transaction_file_path,
                stage="organize",
                processed_files=index,
                total_files=total,
                message="Organization in progress.",
            )
        if progress and last_index > 0 and last_index % ORGANIZE_PROGRESS_EVERY != 0:
            progress_total = total if total > 0 else last_index
            progress(
                OperationProgress(
                    stage=OperationStage.ORGANIZING,
                    processed_files=last_index,
                    total_files=progress_total,
                    message="Organizing files",
                )
            )
        self._update_transaction_checkpoint(
            transaction=transaction,
            transaction_service=transaction_service,
            transaction_file_path=transaction_file_path,
            stage="organize",
            processed_files=last_index,
            total_files=total,
            message="Organization stage completed.",
            force=True,
        )

    def _append_transaction_entry(
        self,
        *,
        transaction: OperationTransaction | None,
        transaction_service: TransactionService | None,
        transaction_file_path: Path | None,
        entry: TransactionEntry,
    ) -> None:
        """Append transaction entry and force flush before mutating filesystem."""
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
        """Rate-limited transaction flush helper used during apply operations."""
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
        """Persist final transaction state at end of apply run."""
        self._flush_transaction(
            transaction,
            transaction_service,
            transaction_file_path,
            force=True,
        )

    def _update_transaction_checkpoint(
        self,
        *,
        transaction: OperationTransaction | None,
        transaction_service: TransactionService | None,
        transaction_file_path: Path | None,
        stage: str,
        processed_files: int,
        total_files: int,
        message: str | None,
        force: bool = False,
    ) -> None:
        """Update transaction checkpoint fields and persist with rate-limited flush."""
        if transaction is None:
            return
        transaction.lifecycle_status = TransactionLifecycleStatus.RUNNING
        transaction.checkpoint_stage = stage
        transaction.checkpoint_processed_files = max(0, processed_files)
        transaction.checkpoint_total_files = max(0, total_files)
        transaction.checkpoint_message = message
        transaction.updated_at_utc = datetime.now(timezone.utc)
        self._flush_transaction(
            transaction,
            transaction_service,
            transaction_file_path,
            force=force,
        )


def safe_relative_path(path: Path, root: Path) -> Path:
    """Return safe relative path; fall back to file name when outside root."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return Path(path.name)

    if str(relative).startswith(".."):
        return Path(path.name)
    return relative


def build_unique_path(path: Path) -> Path:
    """Build a collision-free file path using numbered suffix strategy."""
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
