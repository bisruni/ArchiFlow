"""End-to-end orchestration pipeline joining scan, dedupe, organize and reporting."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from .constants import HASH_CACHE_MAX_ENTRIES, cache_file_path, reports_dir
from .duplicate_detector import DuplicateDetector
from .errors import OperationCancelledError, record_error
from .hash_cache import HashCacheService
from .logger import get_logger
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
    TransactionLifecycleStatus,
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
    """Inputs controlling a single engine run."""

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
    """Outputs produced by an engine run."""

    source_path: Path
    target_path: Path
    summary: OperationSummary
    duplicate_groups: list[DuplicateGroup]
    similar_image_groups: list[SimilarImageGroup]
    transaction_id: str | None
    transaction_file_path: Path | None
    auto_report_json_path: Path | None
    auto_report_csv_path: Path | None


class ArchiFlowEngine:
    """Coordinate scanner, detector, organizer and report exporter services."""

    def __init__(self) -> None:
        """Initialize composed service graph used by engine runs.

        Returns:
            None
        """
        self.logger = get_logger("pipeline")
        self.scanner = FileScanner()
        self.detector = DuplicateDetector()
        self.organizer = FileOrganizer()
        self.transaction_service = TransactionService()
        self.report_exporter = ReportExporter()

    def validate_paths(self, source_path: Path, target_path: Path | None, scope: ExecutionScope) -> str | None:
        """Validate source/target relationship for selected execution scope.

        Args:
            source_path: Source directory path.
            target_path: Target directory path or ``None``.
            scope: Selected execution scope.

        Returns:
            str | None: Error message when invalid, otherwise ``None``.
        """
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
        """Execute configured pipeline stages and return collected result.

        Args:
            options: Run configuration.
            log: Optional text log callback.
            progress: Optional progress callback.
            cancel_event: Shared cancellation event.
            pause_controller: Shared pause controller.

        Returns:
            RunResult: Completed run payload.

        Example:
            >>> # engine.run(options, log=None, progress=None, ...)
            >>> # Produces summary, duplicate groups, reports and transaction info.
        """
        source = ensure_abs(options.source_path)
        target = ensure_abs(options.target_path) if options.target_path else source
        self.logger.info(
            "Run started",
            extra={"transaction_id": ""},
        )

        scanner_errors: list[str] = []
        scanner_skipped: list[str] = []
        files: list[FileRecord] = []
        total_files_scanned = 0
        total_bytes_scanned = 0
        if options.execution_scope.includes_dedupe:
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
            total_files_scanned = len(files)
            total_bytes_scanned = sum(item.size_bytes for item in files)
        elif not options.apply_changes or not options.execution_scope.includes_grouping:
            for record in self.scanner.scan_iter(
                source,
                filter_options=options.filter_options,
                log=log,
                progress=progress,
                errors=scanner_errors,
                skipped_files=scanner_skipped,
                cancel_event=cancel_event,
                pause_controller=pause_controller,
            ):
                total_files_scanned += 1
                total_bytes_scanned += record.size_bytes

        duplicate_groups: list[DuplicateGroup] = []
        similar_groups: list[SimilarImageGroup] = []
        cache: HashCacheService | None = None
        if options.execution_scope.includes_dedupe:
            cache = HashCacheService(cache_file_path(source), max_entries=HASH_CACHE_MAX_ENTRIES)
            try:
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
            finally:
                cache.flush()
                if log is not None:
                    stats = cache.get_stats()
                    lock_wait_ms = stats["lock_wait_ns"] / 1_000_000
                    lock_avg_us = (
                        (stats["lock_wait_ns"] / max(1, stats["lock_acquires"])) / 1_000
                        if stats["lock_acquires"] > 0
                        else 0.0
                    )
                    log(
                        "Hash cache: "
                        f"hits={stats['hits']} misses={stats['misses']} computes={stats['computes']} "
                        f"evictions={stats['evictions']} invalidations={stats['invalidations']} "
                        f"lock_wait_ms={lock_wait_ms:.2f} lock_avg_wait_us={lock_avg_us:.2f}"
                    )

        summary = self._build_summary(
            total_files_scanned=total_files_scanned,
            total_bytes_scanned=total_bytes_scanned,
            duplicate_groups=duplicate_groups,
        )

        transaction: OperationTransaction | None = None
        transaction_path: Path | None = None

        if options.apply_changes:
            transaction = OperationTransaction(
                transaction_id=uuid.uuid4().hex,
                created_at_utc=datetime.now(tz=timezone.utc),
                source_root=source,
                target_root=target,
                entries=[],
                lifecycle_status=TransactionLifecycleStatus.RUNNING,
                checkpoint_stage="created",
                checkpoint_message="Transaction created.",
                updated_at_utc=datetime.now(tz=timezone.utc),
            )
            if not options.dry_run:
                recoverable = self.transaction_service.find_recoverable_transactions(target)
                if recoverable and log is not None:
                    log(
                        f"Uyari: {len(recoverable)} yarim kalmis islem bulundu. "
                        "Gerekirse geri alma/recovery calistirin."
                    )
                # Create transaction journal before any filesystem mutation.
                transaction_path = self.transaction_service.save_transaction(transaction)
                self.logger.info(
                    f"Transaction created: {transaction_path}",
                    extra={"transaction_id": transaction.transaction_id},
                )

            try:
                to_skip: list[FileRecord] = []
                if options.execution_scope.includes_dedupe:
                    self._set_transaction_checkpoint(
                        transaction=transaction,
                        transaction_path=transaction_path,
                        stage="dedupe",
                        message="Duplicate stage started.",
                    )
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
                    self._set_transaction_checkpoint(
                        transaction=transaction,
                        transaction_path=transaction_path,
                        stage="organize",
                        message="Organization stage started.",
                    )
                    remaining: Iterator[FileRecord]
                    if options.execution_scope.includes_dedupe:
                        skip_set = {str(item.full_path).lower() for item in to_skip}
                        remaining_total = len(files) - len(to_skip)
                        remaining = (item for item in files if str(item.full_path).lower() not in skip_set)
                    else:

                        def stream_for_grouping() -> Iterator[FileRecord]:
                            nonlocal total_files_scanned, total_bytes_scanned
                            for item in self.scanner.scan_iter(
                                source,
                                filter_options=options.filter_options,
                                log=log,
                                progress=progress,
                                errors=scanner_errors,
                                skipped_files=scanner_skipped,
                                cancel_event=cancel_event,
                                pause_controller=pause_controller,
                            ):
                                total_files_scanned += 1
                                total_bytes_scanned += item.size_bytes
                                yield item

                        remaining_total = None
                        remaining = stream_for_grouping()
                    self.organizer.organize_by_category_and_date(
                        remaining,
                        total_files=max(0, remaining_total) if remaining_total is not None else None,
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
                self._set_transaction_checkpoint(
                    transaction=transaction,
                    transaction_path=transaction_path,
                    stage="completed",
                    message="Apply run completed.",
                    lifecycle_status=TransactionLifecycleStatus.COMPLETED,
                )
            except OperationCancelledError as exc:
                self._set_transaction_checkpoint(
                    transaction=transaction,
                    transaction_path=transaction_path,
                    stage="cancelled",
                    message="Apply run cancelled.",
                    lifecycle_status=TransactionLifecycleStatus.CANCELLED,
                    interruption_reason=str(exc) or "cancelled",
                )
                raise
            except Exception as exc:
                self._set_transaction_checkpoint(
                    transaction=transaction,
                    transaction_path=transaction_path,
                    stage="failed",
                    message="Apply run failed.",
                    lifecycle_status=TransactionLifecycleStatus.FAILED,
                    interruption_reason=str(exc),
                )
                raise
            finally:
                if not options.dry_run and transaction_path is not None:
                    self.organizer.finalize_transaction_journal(
                        transaction,
                        self.transaction_service,
                        transaction_path,
                    )
                    self.logger.info(
                        f"Transaction finalized: {transaction_path}",
                        extra={"transaction_id": transaction.transaction_id if transaction else ""},
                    )

        summary.total_files_scanned = total_files_scanned
        summary.total_bytes_scanned = total_bytes_scanned
        summary.errors.extend(scanner_errors)
        summary.skipped_files.extend(scanner_skipped)

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
        self.logger.info(
            "Run completed",
            extra={"transaction_id": result.transaction_id or ""},
        )

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
        """Create report model from run result with current timestamp.

        Args:
            result: Completed run output.

        Returns:
            OperationReportData: Report model to export.
        """
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
    def _build_summary(
        *,
        total_files_scanned: int,
        total_bytes_scanned: int,
        duplicate_groups: list[DuplicateGroup],
    ) -> OperationSummary:
        """Compute aggregate summary fields from scanned files and duplicate groups.

        Args:
            total_files_scanned: Total scanned file count.
            total_bytes_scanned: Total scanned byte count.
            duplicate_groups: Duplicate groups found in scan.

        Returns:
            OperationSummary: Aggregated counters.
        """
        duplicate_files = sum(max(0, len(group.files) - 1) for group in duplicate_groups)
        duplicate_bytes = sum(group.size_bytes * max(0, len(group.files) - 1) for group in duplicate_groups)
        return OperationSummary(
            total_files_scanned=total_files_scanned,
            total_bytes_scanned=total_bytes_scanned,
            duplicate_group_count=len(duplicate_groups),
            duplicate_files_found=duplicate_files,
            duplicate_bytes_reclaimable=duplicate_bytes,
        )

    def _auto_export_reports(self, result: RunResult, *, log: LogFn | None) -> None:
        """Write auto JSON/CSV reports under target report directory."""
        try:
            report_dir = reports_dir(result.target_path)
            report = self.build_report(result)
            json_path, csv_path, _pdf_path = self.report_exporter.export(report, report_dir)
            result.auto_report_json_path = json_path
            result.auto_report_csv_path = csv_path
            if log:
                log(f"Rapor yazildi: {json_path.name}, {csv_path.name}")
        except (OSError, IOError) as exc:  # Report export file I/O failures
            message = record_error(
                result.summary.errors,
                log=log,
                operation="Report export failed",
                path=reports_dir(result.target_path),
                error=exc,
            )
            self.logger.error(
                message,
                extra={"transaction_id": result.transaction_id or ""},
            )

    def _set_transaction_checkpoint(
        self,
        *,
        transaction: OperationTransaction | None,
        transaction_path: Path | None,
        stage: str,
        message: str,
        lifecycle_status: TransactionLifecycleStatus = TransactionLifecycleStatus.RUNNING,
        interruption_reason: str | None = None,
    ) -> None:
        """Update transaction checkpoint metadata and persist to journal."""
        if transaction is None or transaction_path is None:
            return
        transaction.lifecycle_status = lifecycle_status
        transaction.checkpoint_stage = stage
        transaction.checkpoint_message = message
        transaction.updated_at_utc = datetime.now(tz=timezone.utc)
        transaction.interruption_reason = interruption_reason
        self.transaction_service.save_transaction_to_path(transaction, transaction_path)
