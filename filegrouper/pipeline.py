from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .duplicate_detector import DuplicateDetector
from .hash_cache import HashCacheService
from .models import (
    DedupeMode,
    DuplicateGroup,
    ExecutionScope,
    FileRecord,
    OperationProgress,
    OperationReportData,
    OperationStage,
    OperationSummary,
    OperationTransaction,
    OrganizationMode,
    ScanFilterOptions,
    SimilarImageGroup,
)
from .organizer import FileOrganizer
from .pause_controller import PauseController
from .report_exporter import ReportExporter
from .scanner import FileScanner
from .transaction_service import TransactionService
from .utils import ensure_abs, is_sub_path, paths_equal

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


@dataclass(slots=True)
class RunOptions:
    source_path: Path
    target_path: Path | None
    organization_mode: OrganizationMode
    dedupe_mode: DedupeMode
    execution_scope: ExecutionScope
    dry_run: bool
    detect_similar_images: bool
    apply_changes: bool
    filter_options: ScanFilterOptions


@dataclass(slots=True)
class RunResult:
    source_path: Path
    target_path: Path
    summary: OperationSummary
    duplicate_groups: list[DuplicateGroup]
    similar_image_groups: list[SimilarImageGroup]
    transaction_file_path: Path | None


class FileGrouperEngine:
    def __init__(self) -> None:
        self.scanner = FileScanner()
        self.detector = DuplicateDetector()
        self.organizer = FileOrganizer()
        self.transaction_service = TransactionService()
        self.report_exporter = ReportExporter()

    def validate_paths(self, source_path: Path, target_path: Path | None, scope: ExecutionScope) -> str | None:
        if not source_path:
            return "Kaynak klasor secin."

        source = ensure_abs(source_path)
        if not source.is_dir():
            return "Kaynak klasor bulunamadi."

        if not scope.includes_grouping:
            return None

        if target_path is None:
            return "Gruplama icin hedef klasor secin."

        target = ensure_abs(target_path)
        if paths_equal(source, target):
            return "Kaynak ve hedef ayni klasor olamaz."

        if is_sub_path(target, source):
            return "Hedef klasor kaynak klasorun icinde olamaz."

        return None

    def run(
        self,
        options: RunOptions,
        *,
        log: LogFn | None,
        progress: ProgressFn | None,
        cancel_event: threading.Event,
        pause_controller: PauseController,
    ) -> RunResult:
        source = ensure_abs(options.source_path)
        target = ensure_abs(options.target_path) if options.target_path else source

        files = self.scanner.scan(
            source,
            filter_options=options.filter_options,
            log=log,
            progress=progress,
            cancel_event=cancel_event,
            pause_controller=pause_controller,
        )

        duplicate_groups: list[DuplicateGroup] = []
        similar_groups: list[SimilarImageGroup] = []
        if options.execution_scope.includes_dedupe:
            cache = HashCacheService(source / ".filegrouper" / "cache" / "hash-cache.json")
            duplicate_groups, similar_groups = self.detector.find_duplicates(
                files,
                cache=cache,
                detect_similar_images=options.detect_similar_images,
                similar_max_distance=8,
                log=log,
                progress=progress,
                cancel_event=cancel_event,
                pause_controller=pause_controller,
            )

        summary = self._build_summary(files, duplicate_groups)

        transaction: OperationTransaction | None = None
        transaction_path: Path | None = None

        if options.apply_changes:
            transaction = OperationTransaction(
                transaction_id=uuid.uuid4().hex,
                created_at_utc=datetime.now(tz=timezone.utc),
                source_root=source,
                target_root=target,
                entries=[],
            )

            to_skip: list[FileRecord] = []
            if options.execution_scope.includes_dedupe:
                to_skip = self.organizer.process_duplicates(
                    duplicate_groups,
                    dedupe_mode=options.dedupe_mode,
                    source_root=source,
                    dry_run=options.dry_run,
                    summary=summary,
                    transaction=transaction,
                    log=log,
                    progress=progress,
                    cancel_event=cancel_event,
                    pause_controller=pause_controller,
                )

            if options.execution_scope.includes_grouping:
                skip_set = {str(item.full_path).lower() for item in to_skip}
                remaining = [item for item in files if str(item.full_path).lower() not in skip_set]
                self.organizer.organize_by_category_and_date(
                    remaining,
                    target_root=target,
                    mode=options.organization_mode,
                    dry_run=options.dry_run,
                    summary=summary,
                    transaction=transaction,
                    log=log,
                    progress=progress,
                    cancel_event=cancel_event,
                    pause_controller=pause_controller,
                )

            if not options.dry_run and transaction.entries:
                transaction_path = self.transaction_service.save_transaction(transaction)

        if progress:
            progress(
                OperationProgress(
                    stage=OperationStage.COMPLETED,
                    processed_files=summary.total_files_scanned,
                    total_files=summary.total_files_scanned,
                    message="Completed",
                )
            )

        return RunResult(
            source_path=source,
            target_path=target,
            summary=summary,
            duplicate_groups=duplicate_groups,
            similar_image_groups=similar_groups,
            transaction_file_path=transaction_path,
        )

    def build_report(self, result: RunResult) -> OperationReportData:
        return OperationReportData(
            generated_at_utc=datetime.now(tz=timezone.utc),
            source_path=result.source_path,
            target_path=result.target_path,
            summary=result.summary,
            duplicate_groups=result.duplicate_groups,
            similar_image_groups=result.similar_image_groups,
            transaction_file_path=result.transaction_file_path,
        )

    @staticmethod
    def _build_summary(files: list[FileRecord], duplicate_groups: list[DuplicateGroup]) -> OperationSummary:
        duplicate_files = sum(max(0, len(group.files) - 1) for group in duplicate_groups)
        duplicate_bytes = sum(group.size_bytes * max(0, len(group.files) - 1) for group in duplicate_groups)
        return OperationSummary(
            total_files_scanned=len(files),
            total_bytes_scanned=sum(item.size_bytes for item in files),
            duplicate_group_count=len(duplicate_groups),
            duplicate_files_found=duplicate_files,
            duplicate_bytes_reclaimable=duplicate_bytes,
        )
