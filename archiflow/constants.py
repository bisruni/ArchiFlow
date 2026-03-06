"""Shared constants and path helpers used across ArchiFlow modules."""

from __future__ import annotations

from pathlib import Path

APP_STATE_DIRNAME = ".archiflow"
QUARANTINE_DIRNAME = ".archiflow_quarantine"
LEGACY_QUARANTINE_DIRNAME = "duplicates_quarantine"
CACHE_DIRNAME = "cache"
TRANSACTIONS_DIRNAME = "transactions"
REPORTS_DIRNAME = "reports"
LOGS_DIRNAME = "logs"
HASH_CACHE_FILENAME = "hash-cache.json"
HASH_CACHE_MAX_ENTRIES = 200000
CONFIG_FILENAME = "config.yaml"

SCAN_PROGRESS_EVERY = 100
ORGANIZE_PROGRESS_EVERY = 50
DUPLICATE_PROGRESS_EVERY = 50
QUICK_HASH_PROGRESS_EVERY = 200
FULL_HASH_PROGRESS_EVERY = 100
SIMILAR_PROGRESS_EVERY = 2000
HASH_PARALLEL_MIN_FILES = 8
HASH_PARALLEL_MAX_WORKERS = 8
SIMILAR_BUCKET_SIZE_LIMIT = 2048
SIMILAR_SECONDARY_BITS = 8

TX_FLUSH_INTERVAL_SECONDS = 1.0
TX_FLUSH_UPDATE_THRESHOLD = 25


def app_state_dir(root: Path) -> Path:
    """Return application state directory under the given root path."""
    return root / APP_STATE_DIRNAME


def cache_file_path(root: Path) -> Path:
    """Return hash cache file path under source root."""
    return app_state_dir(root) / CACHE_DIRNAME / HASH_CACHE_FILENAME


def config_file_path(root: Path) -> Path:
    """Return application config file path under root state directory."""
    return app_state_dir(root) / CONFIG_FILENAME


def reports_dir(root: Path) -> Path:
    """Return report output directory under target root."""
    return app_state_dir(root) / REPORTS_DIRNAME


def transactions_dir(root: Path) -> Path:
    """Return transaction journal directory under target root."""
    return app_state_dir(root) / TRANSACTIONS_DIRNAME


def quarantine_dir(root: Path) -> Path:
    """Return duplicate quarantine root under target root."""
    return root / QUARANTINE_DIRNAME
