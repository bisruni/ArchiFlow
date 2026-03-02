from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .classifier import classify
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
        cancel_event: threading.Event | None = None,
        pause_controller=None,
    ) -> list[FileRecord]:
        source_path = source_path.expanduser().resolve()
        if not source_path.is_dir():
            raise FileNotFoundError(f"Source folder not found: {source_path}")

        records: list[FileRecord] = []
        scanned = 0

        for full_path in self._iter_files(source_path, log):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)

            path = Path(full_path)
            try:
                if filter_options is not None and not filter_options.is_match(path):
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
            except Exception as exc:  # noqa: BLE001
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

    def _iter_files(self, root: Path, log: LogFn | None):
        pending: list[Path] = [root]
        while pending:
            current = pending.pop()

            try:
                with os.scandir(current) as entries:
                    files: list[Path] = []
                    dirs: list[Path] = []
                    for entry in entries:
                        path = Path(entry.path)
                        if entry.is_file(follow_symlinks=False):
                            files.append(path)
                        elif entry.is_dir(follow_symlinks=False):
                            dirs.append(path)
            except Exception as exc:  # noqa: BLE001
                if log:
                    log(f"Could not read folder '{current}': {exc}")
                continue

            for file_path in files:
                yield str(file_path)

            for dir_path in dirs:
                name = dir_path.name.lower()
                if name in {"duplicates_quarantine", ".filegrouper"}:
                    continue
                pending.append(dir_path)


class OperationCancelledError(RuntimeError):
    pass
