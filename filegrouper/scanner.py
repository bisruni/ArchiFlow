from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .classifier import classify
from .errors import OperationCancelledError
from .models import FileRecord, OperationProgress, OperationStage, ScanFilterOptions

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


class FileScanner:
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
        pause_controller=None,
    ) -> list[FileRecord]:
        source_path = source_path.expanduser().resolve()
        if not source_path.is_dir():
            raise FileNotFoundError(f"Source folder not found: {source_path}")

        records: list[FileRecord] = []
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
                records.append(
                    FileRecord(
                        full_path=path,
                        extension=path.suffix.lower(),
                        size_bytes=stat.st_size,
                        last_write_utc=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        category=classify(path),
                    )
                )
            except (OSError, IOError, PermissionError) as exc:  # File stat or path issues
                if errors is not None:
                    errors.append(f"Could not inspect file '{path}': {exc}")
                if skipped_files is not None:
                    skipped_files.append(str(path))
                if log:
                    log(f"Could not inspect file '{path}': {exc}")

            scanned += 1
            if progress and scanned % 100 == 0:
                progress(
                    OperationProgress(
                        stage=OperationStage.SCANNING,
                        processed_files=scanned,
                        total_files=0,
                        message="Scanning files",
                    )
                )

        return sorted(records, key=lambda item: (item.category.value, item.last_write_utc, str(item.full_path).lower()))

    def _iter_files(self, root: Path, log: LogFn | None, errors: list[str] | None = None):
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
                if errors is not None:
                    errors.append(f"Could not read folder '{current}': {exc}")
                if log:
                    log(f"Could not read folder '{current}': {exc}")
                continue

            for file_path in files:
                yield str(file_path)

            for dir_path in dirs:
                name = dir_path.name.lower()
                if name in {"duplicates_quarantine", ".filegrouper", ".filegrouper_quarantine"}:
                    continue
                pending.append(dir_path)
