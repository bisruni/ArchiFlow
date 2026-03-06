from __future__ import annotations

import hashlib
import json
import random
import sys
import threading
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from archiflow.models import DedupeMode, ExecutionScope, OrganizationMode, ScanFilterOptions
from archiflow.pause_controller import PauseController
from archiflow.pipeline import ArchiFlowEngine, RunOptions

try:
    import resource
except ImportError:  # pragma: no cover - platform dependent
    resource = None


@dataclass(slots=True)
class PerfDatasetStats:
    """Summary information for generated synthetic performance dataset."""

    files_created: int
    bytes_written: int
    duplicate_files: int
    same_size_variant_files: int


def _deterministic_bytes(token: str, size: int) -> bytes:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=32).digest()
    return (digest * ((size // len(digest)) + 1))[:size]


def generate_perf_dataset(
    root: Path,
    *,
    files: int,
    duplicate_ratio: float,
    same_size_ratio: float,
    seed: int = 42,
) -> PerfDatasetStats:
    """Generate a synthetic directory tree for performance benchmarks.

    Args:
        root: Empty folder where files will be generated.
        files: Total number of files to create.
        duplicate_ratio: Fraction of files that are exact duplicates.
        same_size_ratio: Fraction of files that share size but differ in content.
        seed: Random seed for deterministic generation.

    Returns:
        PerfDatasetStats: Dataset generation summary.
    """
    if files <= 0:
        raise ValueError("files must be > 0")
    if not 0 <= duplicate_ratio <= 1:
        raise ValueError("duplicate_ratio must be between 0 and 1")
    if not 0 <= same_size_ratio <= 1:
        raise ValueError("same_size_ratio must be between 0 and 1")
    if duplicate_ratio + same_size_ratio > 1:
        raise ValueError("duplicate_ratio + same_size_ratio cannot exceed 1")

    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError(f"Dataset folder must be empty: {root}")

    rng = random.Random(seed)
    folders = [
        root / "docs",
        root / "images",
        root / "videos",
        root / "audio",
        root / "misc" / "deep" / "a",
        root / "misc" / "deep" / "b",
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)

    size_pool = [1024, 2048, 4096, 8192, 16384, 32768, 65536, 262144, 1048576]

    duplicate_files = (int(files * duplicate_ratio) // 2) * 2
    same_size_files = int(files * same_size_ratio)
    unique_files = files - duplicate_files - same_size_files
    if unique_files < 0:
        same_size_files += unique_files
        unique_files = 0

    bytes_written = 0
    file_index = 0

    for _ in range(unique_files):
        folder = rng.choice(folders)
        size = rng.choice(size_pool)
        path = folder / f"u_{file_index:06d}.bin"
        data = _deterministic_bytes(f"u:{file_index}:{seed}", size)
        path.write_bytes(data)
        bytes_written += size
        file_index += 1

    for dup_group in range(duplicate_files // 2):
        folder_a = rng.choice(folders)
        folder_b = rng.choice(folders)
        size = rng.choice(size_pool)
        data = _deterministic_bytes(f"d:{dup_group}:{seed}", size)
        path_a = folder_a / f"d_{file_index:06d}.bin"
        path_b = folder_b / f"d_{file_index + 1:06d}.bin"
        path_a.write_bytes(data)
        path_b.write_bytes(data)
        bytes_written += size * 2
        file_index += 2

    for idx in range(same_size_files):
        folder = rng.choice(folders)
        size = rng.choice(size_pool)
        path = folder / f"s_{file_index:06d}.bin"
        data = _deterministic_bytes(f"s:{idx}:{seed}", size)
        path.write_bytes(data)
        bytes_written += size
        file_index += 1

    return PerfDatasetStats(
        files_created=file_index,
        bytes_written=bytes_written,
        duplicate_files=duplicate_files,
        same_size_variant_files=same_size_files,
    )


def run_preview_benchmark(
    *,
    source: Path,
    iterations: int = 1,
    execution_scope: ExecutionScope = ExecutionScope.GROUP_AND_DEDUPE,
) -> dict[str, Any]:
    """Run preview benchmark and return timing/memory/statistics payload."""
    if iterations <= 0:
        raise ValueError("iterations must be > 0")

    timings: list[float] = []
    peak_memories: list[int] = []
    peak_rss_memories: list[int] = []
    files_per_second: list[float] = []
    bytes_per_second: list[float] = []
    summary_payload: dict[str, Any] | None = None

    for _ in range(iterations):
        engine = ArchiFlowEngine()
        options = RunOptions(
            source_path=source,
            target_path=None,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=DedupeMode.QUARANTINE,
            execution_scope=execution_scope,
            dry_run=True,
            detect_similar_images=False,
            apply_changes=False,
            filter_options=ScanFilterOptions(),
        )
        cancel_event = threading.Event()
        pause_controller = PauseController()

        tracemalloc.start()
        start = perf_counter()
        result = engine.run(
            options,
            log=None,
            progress=None,
            cancel_event=cancel_event,
            pause_controller=pause_controller,
        )
        elapsed = perf_counter() - start
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        timings.append(elapsed)
        peak_memories.append(peak)
        if elapsed > 0:
            files_per_second.append(result.summary.total_files_scanned / elapsed)
            bytes_per_second.append(result.summary.total_bytes_scanned / elapsed)
        if resource is not None:
            ru = resource.getrusage(resource.RUSAGE_SELF)
            # Linux: KB, macOS: bytes
            peak_rss_bytes = int(ru.ru_maxrss if sys.platform == "darwin" else ru.ru_maxrss * 1024)
            peak_rss_memories.append(peak_rss_bytes)
        summary_payload = result.summary.to_dict()

    assert summary_payload is not None
    payload: dict[str, Any] = {
        "iterations": iterations,
        "elapsed_seconds": {
            "min": min(timings),
            "max": max(timings),
            "avg": sum(timings) / len(timings),
        },
        "peak_memory_bytes": {
            "min": min(peak_memories),
            "max": max(peak_memories),
            "avg": sum(peak_memories) / len(peak_memories),
        },
        "files_per_second": {
            "min": min(files_per_second),
            "max": max(files_per_second),
            "avg": sum(files_per_second) / len(files_per_second),
        },
        "bytes_per_second": {
            "min": min(bytes_per_second),
            "max": max(bytes_per_second),
            "avg": sum(bytes_per_second) / len(bytes_per_second),
        },
        "summary": summary_payload,
    }
    if peak_rss_memories:
        payload["peak_rss_bytes"] = {
            "min": min(peak_rss_memories),
            "max": max(peak_rss_memories),
            "avg": sum(peak_rss_memories) / len(peak_rss_memories),
        }
    return payload


def compare_with_baseline(
    current: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    max_time_regression: float,
    max_memory_regression: float,
) -> list[str]:
    """Compare benchmark metrics with baseline and return regression issues."""
    issues: list[str] = []
    c_time = float(current["elapsed_seconds"]["avg"])
    b_time = float(baseline["elapsed_seconds"]["avg"])
    c_mem = float(current["peak_memory_bytes"]["avg"])
    b_mem = float(baseline["peak_memory_bytes"]["avg"])

    if b_time > 0 and c_time > b_time * max_time_regression:
        issues.append(f"time regression: current={c_time:.3f}s baseline={b_time:.3f}s limit={max_time_regression:.2f}x")
    if b_mem > 0 and c_mem > b_mem * max_memory_regression:
        issues.append(
            "memory regression: "
            f"current={c_mem / (1024 * 1024):.2f}MB baseline={b_mem / (1024 * 1024):.2f}MB "
            f"limit={max_memory_regression:.2f}x"
        )
    return issues


def save_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON payload to disk with deterministic formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
