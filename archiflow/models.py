"""Domain models and enums shared across CLI, GUI and services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class FileCategory(str, Enum):
    """High-level file categories used for organization."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    APPLICATION = "application"
    ARCHIVE = "archive"
    OTHER = "other"


class OrganizationMode(str, Enum):
    """Organization operation mode."""

    COPY = "copy"
    MOVE = "move"


class DedupeMode(str, Enum):
    """Duplicate handling mode."""

    OFF = "off"
    QUARANTINE = "quarantine"
    DELETE = "delete"


class ExecutionScope(str, Enum):
    """Scope that selects which pipeline stages will run."""

    GROUP_AND_DEDUPE = "group_and_dedupe"
    GROUP_ONLY = "group_only"
    DEDUPE_ONLY = "dedupe_only"

    @property
    def includes_grouping(self) -> bool:
        """Return whether grouping/organizing stage is included."""
        return self is not ExecutionScope.DEDUPE_ONLY

    @property
    def includes_dedupe(self) -> bool:
        """Return whether duplicate analysis/cleanup stage is included."""
        return self is not ExecutionScope.GROUP_ONLY


class OperationStage(str, Enum):
    """Pipeline progress stages used by UI and CLI."""

    IDLE = "idle"
    SCANNING = "scanning"
    HASHING = "hashing"
    SIMILARITY = "similarity"
    ORGANIZING = "organizing"
    REPORTING = "reporting"
    UNDO = "undo"
    COMPLETED = "completed"


class TransactionAction(str, Enum):
    """Action types tracked in transaction journal entries."""

    COPIED = "copied"
    MOVED = "moved"
    QUARANTINED_DUPLICATE = "quarantined_duplicate"
    DELETED_DUPLICATE = "deleted_duplicate"


class TransactionStatus(str, Enum):
    """Lifecycle state of a transaction entry."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class TransactionLifecycleStatus(str, Enum):
    """Lifecycle state of a full transaction journal."""

    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass(slots=True)
class FileRecord:
    """Normalized scanned file metadata."""

    full_path: Path
    extension: str
    size_bytes: int
    last_write_utc: datetime
    category: FileCategory

    def to_dict(self) -> dict[str, Any]:
        """Serialize record into JSON-compatible dictionary."""
        return {
            "full_path": str(self.full_path),
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "last_write_utc": self.last_write_utc.isoformat(),
            "category": self.category.value,
        }


@dataclass(slots=True)
class DuplicateGroup:
    """Group of byte-identical files represented by shared SHA-256 hash."""

    sha256_hash: str
    size_bytes: int
    files: list[FileRecord]

    def to_dict(self) -> dict[str, Any]:
        """Serialize duplicate group into JSON-compatible dictionary."""
        return {
            "sha256_hash": self.sha256_hash,
            "size_bytes": self.size_bytes,
            "files": [item.to_dict() for item in self.files],
        }


@dataclass(slots=True)
class SimilarImageGroup:
    """Anchor image and visually similar image paths."""

    anchor_path: Path
    similar_paths: list[Path]
    max_distance: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize similar-image group into JSON-compatible dictionary."""
        return {
            "anchor_path": str(self.anchor_path),
            "similar_paths": [str(path) for path in self.similar_paths],
            "max_distance": self.max_distance,
        }


@dataclass(slots=True)
class OperationProgress:
    """Progress event payload emitted during pipeline execution."""

    stage: OperationStage
    processed_files: int
    total_files: int
    message: str


@dataclass(slots=True)
class ScanFilterOptions:
    """Filter options applied while scanning filesystem entries."""

    include_extensions: list[str] = field(default_factory=list)
    exclude_extensions: list[str] = field(default_factory=list)
    min_size_bytes: int | None = None
    max_size_bytes: int | None = None
    from_utc: datetime | None = None
    to_utc: datetime | None = None
    exclude_hidden: bool = True
    exclude_system: bool = True

    @staticmethod
    def normalize_extension(extension: str | None) -> str:
        """Normalize extension text into canonical '.ext' or empty string."""
        if not extension:
            return ""
        extension = extension.strip().lower()
        if not extension:
            return ""
        if not extension.startswith("."):
            extension = f".{extension}"
        return extension

    def is_match(self, path: Path) -> bool:
        """Return True when path metadata matches active filter constraints."""
        include = {self.normalize_extension(item) for item in self.include_extensions if item.strip()}
        exclude = {self.normalize_extension(item) for item in self.exclude_extensions if item.strip()}

        ext = self.normalize_extension(path.suffix)
        if include and ext not in include:
            return False
        if ext in exclude:
            return False

        try:
            stat = path.stat()
        except OSError:
            return False

        if self.min_size_bytes is not None and stat.st_size < self.min_size_bytes:
            return False
        if self.max_size_bytes is not None and stat.st_size > self.max_size_bytes:
            return False

        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        if self.from_utc is not None and modified < self.from_utc:
            return False
        if self.to_utc is not None and modified > self.to_utc:
            return False

        if self.exclude_hidden and path.name.startswith("."):
            return False

        # Portable approximation: dot-files are hidden on Unix. System files are
        # platform specific and intentionally no-op in this Python port.
        return True


@dataclass(slots=True)
class OperationSummary:
    """Aggregated counters and errors produced by a run."""

    total_files_scanned: int = 0
    total_bytes_scanned: int = 0
    duplicate_group_count: int = 0
    duplicate_files_found: int = 0
    duplicate_bytes_reclaimable: int = 0
    files_copied: int = 0
    files_moved: int = 0
    duplicates_quarantined: int = 0
    duplicates_deleted: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize summary into JSON-compatible dictionary."""
        return {
            "total_files_scanned": self.total_files_scanned,
            "total_bytes_scanned": self.total_bytes_scanned,
            "duplicate_group_count": self.duplicate_group_count,
            "duplicate_files_found": self.duplicate_files_found,
            "duplicate_bytes_reclaimable": self.duplicate_bytes_reclaimable,
            "files_copied": self.files_copied,
            "files_moved": self.files_moved,
            "duplicates_quarantined": self.duplicates_quarantined,
            "duplicates_deleted": self.duplicates_deleted,
            "errors": list(self.errors),
            "skipped_files": list(self.skipped_files),
        }


@dataclass(slots=True)
class OperationProfile:
    """Reusable profile of run options for GUI/CLI convenience."""

    name: str
    execution_scope: ExecutionScope = ExecutionScope.GROUP_AND_DEDUPE
    organization_mode: OrganizationMode = OrganizationMode.COPY
    dedupe_mode: DedupeMode = DedupeMode.QUARANTINE
    is_dry_run: bool = True
    detect_similar_images: bool = False
    filter_options: ScanFilterOptions = field(default_factory=ScanFilterOptions)

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile into JSON-compatible dictionary."""
        return {
            "name": self.name,
            "execution_scope": self.execution_scope.value,
            "organization_mode": self.organization_mode.value,
            "dedupe_mode": self.dedupe_mode.value,
            "is_dry_run": self.is_dry_run,
            "detect_similar_images": self.detect_similar_images,
            "filter_options": {
                "include_extensions": list(self.filter_options.include_extensions),
                "exclude_extensions": list(self.filter_options.exclude_extensions),
                "min_size_bytes": self.filter_options.min_size_bytes,
                "max_size_bytes": self.filter_options.max_size_bytes,
                "from_utc": self.filter_options.from_utc.isoformat() if self.filter_options.from_utc else None,
                "to_utc": self.filter_options.to_utc.isoformat() if self.filter_options.to_utc else None,
                "exclude_hidden": self.filter_options.exclude_hidden,
                "exclude_system": self.filter_options.exclude_system,
            },
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "OperationProfile":
        """Create profile model from dictionary payload."""
        options_payload = payload.get("filter_options") or {}

        from_utc = options_payload.get("from_utc")
        to_utc = options_payload.get("to_utc")

        return OperationProfile(
            name=str(payload.get("name", "Unnamed")),
            execution_scope=ExecutionScope(payload.get("execution_scope", ExecutionScope.GROUP_AND_DEDUPE.value)),
            organization_mode=OrganizationMode(payload.get("organization_mode", OrganizationMode.COPY.value)),
            dedupe_mode=DedupeMode(payload.get("dedupe_mode", DedupeMode.QUARANTINE.value)),
            is_dry_run=bool(payload.get("is_dry_run", True)),
            detect_similar_images=bool(payload.get("detect_similar_images", False)),
            filter_options=ScanFilterOptions(
                include_extensions=list(options_payload.get("include_extensions") or []),
                exclude_extensions=list(options_payload.get("exclude_extensions") or []),
                min_size_bytes=options_payload.get("min_size_bytes"),
                max_size_bytes=options_payload.get("max_size_bytes"),
                from_utc=datetime.fromisoformat(from_utc) if from_utc else None,
                to_utc=datetime.fromisoformat(to_utc) if to_utc else None,
                exclude_hidden=bool(options_payload.get("exclude_hidden", True)),
                exclude_system=bool(options_payload.get("exclude_system", True)),
            ),
        )


@dataclass(slots=True)
class TransactionEntry:
    """Single reversible or irreversible filesystem mutation record."""

    action: TransactionAction
    source_path: Path
    destination_path: Path | None
    timestamp_utc: datetime
    status: TransactionStatus = TransactionStatus.PENDING
    error_message: str | None = None
    reversible: bool = True  # Can this action be undone?

    def to_dict(self) -> dict[str, Any]:
        """Serialize transaction entry into JSON-compatible dictionary."""
        return {
            "action": self.action.value,
            "source_path": str(self.source_path),
            "destination_path": str(self.destination_path) if self.destination_path else None,
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "status": self.status.value,
            "error_message": self.error_message,
            "reversible": self.reversible,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "TransactionEntry":
        """Create transaction entry from persisted dictionary payload."""
        destination = payload.get("destination_path")
        return TransactionEntry(
            action=TransactionAction(payload["action"]),
            source_path=Path(payload["source_path"]),
            destination_path=Path(destination) if destination else None,
            timestamp_utc=datetime.fromisoformat(payload["timestamp_utc"]),
            status=TransactionStatus(payload.get("status", TransactionStatus.DONE.value)),
            error_message=payload.get("error_message"),
            reversible=payload.get("reversible", True),
        )


@dataclass(slots=True)
class OperationTransaction:
    """Transaction journal containing ordered filesystem mutation entries."""

    transaction_id: str
    created_at_utc: datetime
    source_root: Path
    target_root: Path
    entries: list[TransactionEntry] = field(default_factory=list)
    lifecycle_status: TransactionLifecycleStatus = TransactionLifecycleStatus.RUNNING
    checkpoint_stage: str = "initialized"
    checkpoint_processed_files: int = 0
    checkpoint_total_files: int = 0
    checkpoint_message: str | None = None
    updated_at_utc: datetime | None = None
    interruption_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize transaction journal into JSON-compatible dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "created_at_utc": self.created_at_utc.isoformat(),
            "source_root": str(self.source_root),
            "target_root": str(self.target_root),
            "entries": [entry.to_dict() for entry in self.entries],
            "lifecycle_status": self.lifecycle_status.value,
            "checkpoint_stage": self.checkpoint_stage,
            "checkpoint_processed_files": self.checkpoint_processed_files,
            "checkpoint_total_files": self.checkpoint_total_files,
            "checkpoint_message": self.checkpoint_message,
            "updated_at_utc": self.updated_at_utc.isoformat() if self.updated_at_utc else None,
            "interruption_reason": self.interruption_reason,
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "OperationTransaction":
        """Create transaction journal model from persisted payload."""
        updated_at = payload.get("updated_at_utc")
        return OperationTransaction(
            transaction_id=payload["transaction_id"],
            created_at_utc=datetime.fromisoformat(payload["created_at_utc"]),
            source_root=Path(payload["source_root"]),
            target_root=Path(payload["target_root"]),
            entries=[TransactionEntry.from_dict(item) for item in payload.get("entries") or []],
            lifecycle_status=TransactionLifecycleStatus(
                payload.get("lifecycle_status", TransactionLifecycleStatus.COMPLETED.value)
            ),
            checkpoint_stage=str(payload.get("checkpoint_stage", "legacy")),
            checkpoint_processed_files=int(payload.get("checkpoint_processed_files", 0)),
            checkpoint_total_files=int(payload.get("checkpoint_total_files", 0)),
            checkpoint_message=payload.get("checkpoint_message"),
            updated_at_utc=datetime.fromisoformat(updated_at) if updated_at else None,
            interruption_reason=payload.get("interruption_reason"),
        )


@dataclass(slots=True)
class OperationReportData:
    """Report payload exported after run completion."""

    generated_at_utc: datetime
    source_path: Path
    target_path: Path
    summary: OperationSummary
    duplicate_groups: list[DuplicateGroup]
    similar_image_groups: list[SimilarImageGroup]
    transaction_id: str | None
    transaction_file_path: Path | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize report payload into JSON-compatible dictionary."""
        return {
            "generated_at_utc": self.generated_at_utc.isoformat(),
            "source_path": str(self.source_path),
            "target_path": str(self.target_path),
            "summary": self.summary.to_dict(),
            "duplicate_groups": [group.to_dict() for group in self.duplicate_groups],
            "similar_image_groups": [group.to_dict() for group in self.similar_image_groups],
            "transaction_id": self.transaction_id,
            "transaction_file_path": str(self.transaction_file_path) if self.transaction_file_path else None,
        }
