"""Filesystem scanning service producing normalized FileRecord entries."""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from .classifier import classify
from .constants import APP_STATE_DIRNAME, LEGACY_QUARANTINE_DIRNAME, QUARANTINE_DIRNAME, SCAN_PROGRESS_EVERY
from .errors import OperationCancelledError, record_error
from .models import FileRecord, OperationProgress, OperationStage, ScanFilterOptions
from .pause_controller import PauseController

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


class FileScanner:
    """Traverse source tree, apply filters, and collect file metadata records."""

    def scan_iter(
        self,
        source_path: Path,
        *,
        filter_options: ScanFilterOptions | None = None,
        log: LogFn | None = None,
        progress: ProgressFn | None = None,
        errors: list[str] | None = None,
        skipped_files: list[str] | None = None,
        cancel_event: threading.Event | None = None,
        pause_controller: PauseController | None = None,
    ) -> Iterator[FileRecord]:
        """Yield matching file records lazily while scanning the source tree."""
        source_path = source_path.expanduser().resolve()
        if not source_path.is_dir():
            raise FileNotFoundError(f"Source folder not found: {source_path}")

        scanned = 0
        for full_path in self._iter_files(source_path, log, errors):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)

            path = Path(full_path)
            try:
                if filter_options is not None and not filter_options.is_match(path):
                    if skipped_files is not None:
                        skipped_files.append(str(path))
                    continue

                stat = path.stat()
                yield FileRecord(
                    full_path=path,
                    extension=path.suffix.lower(),
                    size_bytes=stat.st_size,
                    last_write_utc=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    category=classify(path),
                )
            except (OSError, IOError, PermissionError) as exc:  # File stat or path issues
                record_error(
                    errors,
                    log=log,
                    operation="Could not inspect file",
                    path=path,
                    error=exc,
                )
                if skipped_files is not None:
                    skipped_files.append(str(path))

            scanned += 1
            if progress and scanned % SCAN_PROGRESS_EVERY == 0:
                progress(
                    OperationProgress(
                        stage=OperationStage.SCANNING,
                        processed_files=scanned,
                        total_files=0,
                        message="Scanning files",
                    )
                )

    def scan(
        self,
        source_path: Path,
        *,
        filter_options: ScanFilterOptions | None = None,
        log: LogFn | None = None,
        progress: ProgressFn | None = None,
        errors: list[str] | None = None,
        skipped_files: list[str] | None = None,
        cancel_event: threading.Event | None = None,
        pause_controller: PauseController | None = None,
    ) -> list[FileRecord]:
        """Scan a source folder and return sorted records matching filters."""
        records = list(
            self.scan_iter(
                source_path,
                filter_options=filter_options,
                log=log,
                progress=progress,
                errors=errors,
                skipped_files=skipped_files,
                cancel_event=cancel_event,
                pause_controller=pause_controller,
            )
        )
        return sorted(records, key=lambda item: (item.category.value, item.last_write_utc, str(item.full_path).lower()))

    def _iter_files(self, root: Path, log: LogFn | None, errors: list[str] | None = None) -> Iterator[str]:
        """Yield file paths breadth-first while safely skipping bad entries."""
        pending: list[Path] = [root]
        while pending:
            current = pending.pop()

            try:
                with os.scandir(current) as entries:
                    files: list[Path] = []
                    dirs: list[Path] = []
                    for entry in entries:
                        path = Path(entry.path)
                        if entry.is_symlink():
                            # Broken/unsupported symlinks are intentionally skipped for stability.
                            continue
                        if entry.is_file(follow_symlinks=False):
                            files.append(path)
                        elif entry.is_dir(follow_symlinks=False):
                            dirs.append(path)
            except (OSError, IOError, PermissionError) as exc:  # Directory iteration issues
                record_error(
                    errors,
                    log=log,
                    operation="Could not read folder",
                    path=current,
                    error=exc,
                )
                continue

            for file_path in files:
                yield str(file_path)

            for dir_path in dirs:
                name = dir_path.name.lower()
                if name in {LEGACY_QUARANTINE_DIRNAME, APP_STATE_DIRNAME, QUARANTINE_DIRNAME}:
                    continue
                pending.append(dir_path)
