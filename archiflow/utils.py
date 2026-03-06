"""General-purpose helpers shared across modules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def format_size(num_bytes: int) -> str:
    """Format bytes as a compact human-readable size string."""
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(num_bytes)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.2f} {units[unit_index]}"


def now_utc() -> datetime:
    """Return current UTC timestamp as timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


def ensure_abs(path: str | Path) -> Path:
    """Expand user markers and return absolute resolved path."""
    return Path(path).expanduser().resolve()


def paths_equal(a: Path, b: Path) -> bool:
    """Check path equality after normalization and resolution."""
    return ensure_abs(a) == ensure_abs(b)


def is_sub_path(candidate: Path, root: Path) -> bool:
    """Return True when candidate is nested inside root path."""
    candidate_abs = ensure_abs(candidate)
    root_abs = ensure_abs(root)
    try:
        candidate_abs.relative_to(root_abs)
        return True
    except ValueError:
        return False
