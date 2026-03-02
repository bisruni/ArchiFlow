from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
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
    duplicate_protected_paths: set[str] = field(default_factory=set)


@dataclass(slots=True)
class RunResult:
    source_path: Path
    target_path: Path
    summary: OperationSummary
    duplicate_groups: list[DuplicateGroup]
    similar_image_groups: list[SimilarImageGroup]
    transaction_id: str | None
    transaction_file_path: Path | None
    auto_report_json_path: Path | None
    auto_report_csv_path: Path | None


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

        scanner_errors: list[str] = []
        scanner_skipped: list[str] = []
        files = self.scanner.scan(
            source,
            filter_options=options.filter_options,
            log=log,
            progress=progress,
            errors=scanner_errors,
            skipped_files=scanner_skipped,
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
            if options.detect_similar_images and log is not None:
                log("Not: Benzer gorseller sadece raporlanir; silme/karantina sadece kesin kopyalara uygulanir.")

        summary = self._build_summary(files, duplicate_groups)
        summary.errors.extend(scanner_errors)
        summary.skipped_files.extend(scanner_skipped)

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
            if not options.dry_run:
                # Create transaction journal before any filesystem mutation.
                transaction_path = self.transaction_service.save_transaction(transaction)

            to_skip: list[FileRecord] = []
            if options.execution_scope.includes_dedupe:
                to_skip = self.organizer.process_duplicates(
                    duplicate_groups,
                    dedupe_mode=options.dedupe_mode,
                    protected_paths=options.duplicate_protected_paths,
                    source_root=source,
                    target_root=target,
                    dry_run=options.dry_run,
                    summary=summary,
                    transaction=transaction,
                    transaction_service=self.transaction_service,
                    transaction_file_path=transaction_path,
                    log=log,
                    progress=progress,
                    cancel_event=cancel_event,
                    pause_controller=pause_controller,
                )

            if options.execution_scope.includes_grouping:
                skip_set = {str(item.full_path).lower() for item in to_skip}
                remaining_total = len(files) - len(to_skip)
                remaining = (item for item in files if str(item.full_path).lower() not in skip_set)
                self.organizer.organize_by_category_and_date(
                    remaining,
                    total_files=max(0, remaining_total),
                    target_root=target,
                    mode=options.organization_mode,
                    dry_run=options.dry_run,
                    summary=summary,
                    transaction=transaction,
                    transaction_service=self.transaction_service,
                    transaction_file_path=transaction_path,
                    log=log,
                    progress=progress,
                    cancel_event=cancel_event,
                    pause_controller=pause_controller,
                )

            if not options.dry_run and transaction_path is not None:
                self.transaction_service.save_transaction_to_path(transaction, transaction_path)

        result = RunResult(
            source_path=source,
            target_path=target,
            summary=summary,
            duplicate_groups=duplicate_groups,
            similar_image_groups=similar_groups,
            transaction_id=transaction.transaction_id if transaction else None,
            transaction_file_path=transaction_path,
            auto_report_json_path=None,
            auto_report_csv_path=None,
        )
        self._auto_export_reports(result, log=log)

        if progress:
            progress(
                OperationProgress(
                    stage=OperationStage.COMPLETED,
                    processed_files=summary.total_files_scanned,
                    total_files=summary.total_files_scanned,
                    message="Completed",
                )
            )

        return result

    def build_report(self, result: RunResult) -> OperationReportData:
        return OperationReportData(
            generated_at_utc=datetime.now(tz=timezone.utc),
            source_path=result.source_path,
            target_path=result.target_path,
            summary=result.summary,
            duplicate_groups=result.duplicate_groups,
            similar_image_groups=result.similar_image_groups,
            transaction_id=result.transaction_id,
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

    def _auto_export_reports(self, result: RunResult, *, log: LogFn | None) -> None:
        try:
            report_dir = result.target_path / ".filegrouper" / "reports"
            report = self.build_report(result)
            json_path, csv_path, _pdf_path = self.report_exporter.export(report, report_dir)
            result.auto_report_json_path = json_path
            result.auto_report_csv_path = csv_path
            if log:
                log(f"Rapor yazildi: {json_path.name}, {csv_path.name}")
        except Exception as exc:  # noqa: BLE001
            result.summary.errors.append(f"Report export failed: {exc}")
            if log:
                log(f"Report export failed: {exc}")
