from __future__ import annotations

import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

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
)

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


class FileOrganizer:
    def process_duplicates(
        self,
        duplicate_groups: list[DuplicateGroup],
        *,
        dedupe_mode: DedupeMode,
        protected_paths: set[str] | None,
        source_root: Path,
        dry_run: bool,
        summary: OperationSummary,
        transaction: OperationTransaction | None,
        log: LogFn | None,
        progress: ProgressFn | None,
        cancel_event: threading.Event | None,
        pause_controller=None,
    ) -> list[FileRecord]:
        if dedupe_mode is DedupeMode.OFF:
            return []

        protected_lookup = {item.lower() for item in (protected_paths or set())}
        unique_remove: dict[str, FileRecord] = {}
        for group in duplicate_groups:
            if len(group.files) < 2:
                continue

            keep_lookup = {
                str(item.full_path).lower()
                for item in group.files
                if str(item.full_path).lower() in protected_lookup
            }
            if not keep_lookup:
                keep_lookup = {str(group.files[0].full_path).lower()}

            for item in group.files:
                if str(item.full_path).lower() in keep_lookup:
                    continue
                unique_remove[str(item.full_path).lower()] = item

        to_remove = list(unique_remove.values())
        if not to_remove:
            return []

        quarantine_root = source_root / "Duplicates_Quarantine" / datetime.now().strftime("%Y%m%d_%H%M%S")

        for index, duplicate in enumerate(to_remove, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)

            if not duplicate.full_path.exists():
                continue

            try:
                if dedupe_mode is DedupeMode.DELETE:
                    if not dry_run:
                        duplicate.full_path.unlink(missing_ok=True)
                    summary.duplicates_deleted += 1
                    if transaction is not None:
                        transaction.entries.append(
                            TransactionEntry(
                                action=TransactionAction.DELETED_DUPLICATE,
                                source_path=duplicate.full_path,
                                destination_path=None,
                                timestamp_utc=datetime.utcnow(),
                            )
                        )
                else:
                    relative = safe_relative_path(duplicate.full_path, source_root)
                    destination = build_unique_path(quarantine_root / relative)

                    if not dry_run:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(duplicate.full_path), str(destination))

                    summary.duplicates_quarantined += 1
                    if transaction is not None:
                        transaction.entries.append(
                            TransactionEntry(
                                action=TransactionAction.QUARANTINED_DUPLICATE,
                                source_path=duplicate.full_path,
                                destination_path=destination,
                                timestamp_utc=datetime.utcnow(),
                            )
                        )
            except Exception as exc:  # noqa: BLE001
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
        files: list[FileRecord],
        *,
        target_root: Path,
        mode: OrganizationMode,
        dry_run: bool,
        summary: OperationSummary,
        transaction: OperationTransaction | None,
        log: LogFn | None,
        progress: ProgressFn | None,
        cancel_event: threading.Event | None,
        pause_controller=None,
    ) -> None:
        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)

        for index, file in enumerate(files, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)

            if not file.full_path.exists():
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
                if mode is OrganizationMode.COPY:
                    shutil.copy2(file.full_path, destination_path)
                    summary.files_copied += 1
                    action = TransactionAction.COPIED
                else:
                    shutil.move(str(file.full_path), str(destination_path))
                    summary.files_moved += 1
                    action = TransactionAction.MOVED

                if transaction is not None:
                    transaction.entries.append(
                        TransactionEntry(
                            action=action,
                            source_path=file.full_path,
                            destination_path=destination_path,
                            timestamp_utc=datetime.utcnow(),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                summary.errors.append(f"Could not process '{file.full_path}': {exc}")
                if log:
                    log(f"Could not process '{file.full_path}': {exc}")

            if progress and index % 50 == 0:
                progress(
                    OperationProgress(
                        stage=OperationStage.ORGANIZING,
                        processed_files=index,
                        total_files=len(files),
                        message="Organizing files",
                    )
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
