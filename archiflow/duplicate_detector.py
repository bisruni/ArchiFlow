"""Duplicate and similar-image detection algorithms."""

from __future__ import annotations

import hashlib
import os
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path
from typing import Any, Callable, Protocol, cast

from .constants import (
    FULL_HASH_PROGRESS_EVERY,
    HASH_PARALLEL_MAX_WORKERS,
    HASH_PARALLEL_MIN_FILES,
    QUICK_HASH_PROGRESS_EVERY,
    SIMILAR_BUCKET_SIZE_LIMIT,
    SIMILAR_PROGRESS_EVERY,
    SIMILAR_SECONDARY_BITS,
)
from .errors import OperationCancelledError, log_error
from .hash_cache import HashCacheService
from .models import DuplicateGroup, FileRecord, OperationProgress, OperationStage, SimilarImageGroup

Image: Any | None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
except ImportError:
    pass

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


class PauseControllerLike(Protocol):
    """Protocol for pause-capable controllers used in long-running loops."""

    def wait_if_paused(self, cancel_event: threading.Event | None) -> None:
        """Block while paused, respecting cancellation."""


SUPPORTED_SIMILAR_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic"})

# Quick signature reads a few slices of the file (fast). Used as stage-1 filter before full SHA.
QUICK_EDGE_BYTES = 1024 * 1024  # first/last 1MB
QUICK_MIDDLE_BYTES = 128 * 1024  # 128KB samples in middle

# Similar image: dHash(64-bit) + banding candidate generation (avoid N^2).
SIMILAR_HASH_BITS = 64
SIMILAR_BAND_BITS = 16
SIMILAR_BAND_COUNT = SIMILAR_HASH_BITS // SIMILAR_BAND_BITS
SIMILAR_MAX_PAIRS = 2_000_000  # hard cap to avoid runaway on huge libraries


class DuplicateDetector:
    """Detect exact duplicates and optional visually similar images."""

    def __init__(self) -> None:
        """Initialize DuplicateDetector with instance state.

        Tracks whether Pillow unavailability warning has been logged
        to avoid duplicate log messages.
        """
        self._similar_unavailable_logged = False

    @staticmethod
    def is_similar_supported() -> bool:
        """Return whether perceptual similar-image mode is available."""
        return Image is not None

    def find_duplicates(
        self,
        files: list[FileRecord],
        *,
        cache: HashCacheService | None,
        detect_similar_images: bool,
        similar_max_distance: int,
        log: LogFn | None,
        progress: ProgressFn | None,
        cancel_event: threading.Event | None,
        pause_controller: PauseControllerLike | None = None,
    ) -> tuple[list[DuplicateGroup], list[SimilarImageGroup]]:
        """Find byte-identical duplicates and optional similar-image groups."""
        # 1) group by size (cheap)
        grouped_by_size: dict[int, list[FileRecord]] = defaultdict(list)
        for file in files:
            grouped_by_size[file.size_bytes].append(file)

        size_candidates = [group for group in grouped_by_size.values() if len(group) > 1]

        # 2) stage-1 quick signature (fast IO) to reduce candidates
        quick_total = sum(len(group) for group in size_candidates)
        quick_processed = 0
        quick_workers = _recommended_hash_workers(quick_total)
        quick_executor: ThreadPoolExecutor | None = None
        if quick_workers > 1 and quick_total >= HASH_PARALLEL_MIN_FILES:
            quick_executor = ThreadPoolExecutor(max_workers=quick_workers)
            if log is not None:
                log(f"Quick signature workers: {quick_workers}")

        hash_input_groups: list[list[FileRecord]] = []
        try:
            for size_group in size_candidates:
                by_quick: dict[str, list[FileRecord]] = defaultdict(list)
                if quick_executor is not None and len(size_group) >= HASH_PARALLEL_MIN_FILES:
                    for file in size_group:
                        _guard_cancel(cancel_event, pause_controller)
                    futures_to_file = {
                        quick_executor.submit(
                            _compute_quick_signature_for_file,
                            file,
                            cache,
                            cancel_event,
                            pause_controller,
                        ): file
                        for file in size_group
                    }

                    for future in as_completed(futures_to_file):
                        file = futures_to_file[future]
                        try:
                            quick_signature = future.result()
                        except OperationCancelledError:
                            if quick_executor is not None:
                                quick_executor.shutdown(wait=False, cancel_futures=True)
                                quick_executor = None
                            raise
                        except (OSError, IOError, ValueError) as exc:  # File I/O or hash computation
                            log_error(
                                log,
                                operation="Could not compute quick signature",
                                path=file.full_path,
                                error=exc,
                            )
                            continue

                        by_quick[quick_signature].append(file)
                        quick_processed += 1
                        if progress and (
                            quick_processed % QUICK_HASH_PROGRESS_EVERY == 0 or quick_processed == quick_total
                        ):
                            progress(
                                OperationProgress(
                                    stage=OperationStage.HASHING,
                                    processed_files=quick_processed,
                                    total_files=max(quick_total, 1),
                                    message="Quick duplicate filtering",
                                )
                            )
                else:
                    for file in size_group:
                        _guard_cancel(cancel_event, pause_controller)

                        try:
                            quick_signature = _compute_quick_signature_for_file(
                                file,
                                cache,
                                cancel_event,
                                pause_controller,
                            )
                        except (OSError, IOError, ValueError) as exc:  # File I/O or hash computation
                            log_error(
                                log,
                                operation="Could not compute quick signature",
                                path=file.full_path,
                                error=exc,
                            )
                            continue

                        by_quick[quick_signature].append(file)
                        quick_processed += 1
                        if progress and (
                            quick_processed % QUICK_HASH_PROGRESS_EVERY == 0 or quick_processed == quick_total
                        ):
                            progress(
                                OperationProgress(
                                    stage=OperationStage.HASHING,
                                    processed_files=quick_processed,
                                    total_files=max(quick_total, 1),
                                    message="Quick duplicate filtering",
                                )
                            )

                for quick_group in by_quick.values():
                    if len(quick_group) > 1:
                        hash_input_groups.append(quick_group)
        finally:
            if quick_executor is not None:
                quick_executor.shutdown(wait=True, cancel_futures=False)

        # 3) stage-2 full SHA only on filtered candidates
        groups: list[DuplicateGroup] = []
        full_total = sum(len(group) for group in hash_input_groups)
        full_processed = 0
        hash_workers = _recommended_hash_workers(full_total)
        executor: ThreadPoolExecutor | None = None
        if hash_workers > 1 and full_total >= HASH_PARALLEL_MIN_FILES:
            executor = ThreadPoolExecutor(max_workers=hash_workers)
            if log is not None:
                log(f"Duplicate hashing workers: {hash_workers}")

        try:
            for candidate_group in hash_input_groups:
                by_hash: dict[str, list[FileRecord]] = defaultdict(list)
                if executor is not None and len(candidate_group) >= HASH_PARALLEL_MIN_FILES:
                    for file in candidate_group:
                        _guard_cancel(cancel_event, pause_controller)
                    futures_to_file = {
                        executor.submit(
                            _compute_sha256_for_file,
                            file,
                            cache,
                            cancel_event,
                            pause_controller,
                        ): file
                        for file in candidate_group
                    }

                    for future in as_completed(futures_to_file):
                        file = futures_to_file[future]
                        try:
                            sha256_hash = future.result()
                        except OperationCancelledError:
                            if executor is not None:
                                executor.shutdown(wait=False, cancel_futures=True)
                                executor = None
                            raise
                        except (OSError, IOError, ValueError) as exc:  # File I/O or hash computation
                            log_error(
                                log,
                                operation="Could not compute sha256",
                                path=file.full_path,
                                error=exc,
                            )
                            continue

                        by_hash[sha256_hash].append(file)
                        full_processed += 1
                        if progress and (
                            full_processed % FULL_HASH_PROGRESS_EVERY == 0 or full_processed == full_total
                        ):
                            progress(
                                OperationProgress(
                                    stage=OperationStage.HASHING,
                                    processed_files=full_processed,
                                    total_files=max(full_total, 1),
                                    message="Computing full hashes",
                                )
                            )
                else:
                    for file in candidate_group:
                        _guard_cancel(cancel_event, pause_controller)

                        try:
                            sha256_hash = _compute_sha256_for_file(
                                file,
                                cache,
                                cancel_event,
                                pause_controller,
                            )
                        except (OSError, IOError, ValueError) as exc:  # File I/O or hash computation
                            log_error(
                                log,
                                operation="Could not compute sha256",
                                path=file.full_path,
                                error=exc,
                            )
                            continue

                        by_hash[sha256_hash].append(file)
                        full_processed += 1
                        if progress and (
                            full_processed % FULL_HASH_PROGRESS_EVERY == 0 or full_processed == full_total
                        ):
                            progress(
                                OperationProgress(
                                    stage=OperationStage.HASHING,
                                    processed_files=full_processed,
                                    total_files=max(full_total, 1),
                                    message="Computing full hashes",
                                )
                            )

                # 4) final safety:
                # even if SHA matches, verify byte-identical to avoid cache/corruption edge-cases
                for sha256_hash, file_list in by_hash.items():
                    if len(file_list) <= 1:
                        continue

                    exact_groups = split_exact_groups(
                        file_list,
                        cancel_event=cancel_event,
                        pause_controller=pause_controller,
                    )

                    for exact_group in exact_groups:
                        if len(exact_group) <= 1:
                            continue
                        ordered = sorted(
                            exact_group, key=lambda item: (item.last_write_utc, str(item.full_path).lower())
                        )
                        groups.append(
                            DuplicateGroup(
                                sha256_hash=sha256_hash,
                                size_bytes=ordered[0].size_bytes,
                                files=ordered,
                            )
                        )
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=False)

        duplicate_groups = sorted(groups, key=lambda item: (-len(item.files), -item.size_bytes, item.sha256_hash))

        # Similar images (optional)
        similar_groups: list[SimilarImageGroup] = []
        if detect_similar_images:
            similar_groups = self.find_similar_images(
                files,
                max_distance=similar_max_distance,
                log=log,
                progress=progress,
                cancel_event=cancel_event,
                pause_controller=pause_controller,
            )

        return duplicate_groups, similar_groups

    def find_similar_images(
        self,
        files: list[FileRecord],
        *,
        max_distance: int,
        log: LogFn | None,
        progress: ProgressFn | None,
        cancel_event: threading.Event | None,
        pause_controller: PauseControllerLike | None = None,
    ) -> list[SimilarImageGroup]:
        """Find visually similar images using dHash and banded candidate search."""
        images = [item for item in files if item.extension in SUPPORTED_SIMILAR_EXTENSIONS]
        if len(images) < 2:
            return []

        if Image is None:
            if log and not self._similar_unavailable_logged:
                log("Similar image detection skipped: Pillow is not installed.")
                self._similar_unavailable_logged = True
            return []

        # 1) compute real perceptual hashes (dHash) from decoded image pixels
        image_hashes: list[tuple[FileRecord, int]] = []
        for index, item in enumerate(images, start=1):
            _guard_cancel(cancel_event, pause_controller)

            try:
                image_hashes.append((item, compute_dhash(item.full_path)))
            except (OSError, ValueError, RuntimeError) as exc:  # Image I/O or processing error
                log_error(
                    log,
                    operation="Could not compute image hash",
                    path=item.full_path,
                    error=exc,
                )

            if progress:
                progress(
                    OperationProgress(
                        stage=OperationStage.SIMILARITY,
                        processed_files=index,
                        total_files=len(images),
                        message="Computing image hashes",
                    )
                )

        if len(image_hashes) < 2:
            return []

        # 2) union-find clustering by hamming distance on streamed candidates (avoid huge pair list in memory)
        parent = list(range(len(image_hashes)))
        rank = [0] * len(image_hashes)

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if rank[ra] < rank[rb]:
                parent[ra] = rb
            elif rank[ra] > rank[rb]:
                parent[rb] = ra
            else:
                parent[rb] = ra
                rank[ra] += 1

        buckets: list[dict[int, list[int]]] = [defaultdict(list) for _ in range(SIMILAR_BAND_COUNT)]
        for idx, (_, h) in enumerate(image_hashes):
            for b in range(SIMILAR_BAND_COUNT):
                shift = b * SIMILAR_BAND_BITS
                band = (h >> shift) & ((1 << SIMILAR_BAND_BITS) - 1)
                buckets[b][band].append(idx)

        seen: set[int] = set()
        compared_pairs = 0
        limited = False
        image_count = len(image_hashes)

        oversized_buckets = 0
        for band_index, bucket_map in enumerate(buckets):
            for indices in bucket_map.values():
                if len(indices) < 2:
                    continue
                candidate_buckets = _split_similar_bucket(indices, image_hashes, band_index)
                if len(indices) > SIMILAR_BUCKET_SIZE_LIMIT:
                    oversized_buckets += 1
                for candidate_indices in candidate_buckets:
                    sorted_indices = sorted(candidate_indices)
                    for i, a_idx in enumerate(sorted_indices):
                        for b_idx in sorted_indices[i + 1 :]:
                            _guard_cancel(cancel_event, pause_controller)

                            pair_key = a_idx * image_count + b_idx
                            if pair_key in seen:
                                continue
                            seen.add(pair_key)
                            compared_pairs += 1

                            a_hash = image_hashes[a_idx][1]
                            b_hash = image_hashes[b_idx][1]
                            if hamming_distance(a_hash, b_hash) <= max_distance:
                                union(a_idx, b_idx)

                            if progress and (compared_pairs % SIMILAR_PROGRESS_EVERY == 0):
                                progress(
                                    OperationProgress(
                                        stage=OperationStage.SIMILARITY,
                                        processed_files=compared_pairs,
                                        total_files=SIMILAR_MAX_PAIRS,
                                        message="Comparing similar images",
                                    )
                                )

                            if compared_pairs >= SIMILAR_MAX_PAIRS:
                                limited = True
                                break
                        if limited:
                            break
                    if limited:
                        break
                if limited:
                    break
            if limited:
                break

        if progress and compared_pairs % SIMILAR_PROGRESS_EVERY != 0 and compared_pairs > 0:
            progress(
                OperationProgress(
                    stage=OperationStage.SIMILARITY,
                    processed_files=compared_pairs,
                    total_files=max(compared_pairs, 1),
                    message="Comparing similar images",
                )
            )
        if limited and log:
            log(f"Similar image candidate pairs limited to {SIMILAR_MAX_PAIRS} for performance.")
        if oversized_buckets > 0 and log:
            log(
                "Similar image optimization: "
                f"{oversized_buckets} large buckets split at {SIMILAR_BUCKET_SIZE_LIMIT} items."
            )

        grouped: dict[int, list[FileRecord]] = defaultdict(list)
        for idx, (item, _) in enumerate(image_hashes):
            grouped[find(idx)].append(item)

        similar_groups: list[SimilarImageGroup] = []
        for items in grouped.values():
            if len(items) < 2:
                continue
            ordered = sorted(items, key=lambda rec: (rec.last_write_utc, str(rec.full_path).lower()))
            similar_groups.append(
                SimilarImageGroup(
                    anchor_path=ordered[0].full_path,
                    similar_paths=[candidate.full_path for candidate in ordered[1:]],
                    max_distance=max_distance,
                )
            )

        similar_groups.sort(key=lambda item: -len(item.similar_paths))
        return similar_groups


def _guard_cancel(
    cancel_event: threading.Event | None,
    pause_controller: PauseControllerLike | None = None,
) -> None:
    """Raise cancellation or block while paused based on runtime controls."""
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelledError()
    if pause_controller is not None:
        pause_controller.wait_if_paused(cancel_event)


def _recommended_hash_workers(total_hash_candidates: int) -> int:
    """Pick an IO-friendly worker count based on dataset size and CPU count."""
    override = os.environ.get("ARCHIFLOW_HASH_WORKERS")
    if override:
        try:
            forced = int(override.strip())
            if forced > 0:
                return forced
        except ValueError:
            pass
    if total_hash_candidates < HASH_PARALLEL_MIN_FILES:
        return 1
    cpu_count = max(1, os.cpu_count() or 4)
    # Hashing is IO-bound on spinning disks and mixed on SSD; 2x CPUs is a practical ceiling.
    upper = min(HASH_PARALLEL_MAX_WORKERS, cpu_count * 2)
    # Avoid over-provisioning for small candidate counts.
    tuned = min(upper, max(1, total_hash_candidates // 2))
    return max(1, tuned)


def _compute_sha256_for_file(
    file: FileRecord,
    cache: HashCacheService | None,
    cancel_event: threading.Event | None,
    pause_controller: PauseControllerLike | None,
) -> str:
    """Compute SHA-256 for a file record using cache when available."""
    if cache is not None:
        return cache.get_or_compute_sha256(
            file.full_path,
            file.size_bytes,
            file.last_write_utc,
            cast(
                Callable[[], str],
                partial(
                    compute_sha256,
                    file.full_path,
                    cancel_event=cancel_event,
                    pause_controller=pause_controller,
                ),
            ),
        )
    return compute_sha256(
        file.full_path,
        cancel_event=cancel_event,
        pause_controller=pause_controller,
    )


def _compute_quick_signature_for_file(
    file: FileRecord,
    cache: HashCacheService | None,
    cancel_event: threading.Event | None,
    pause_controller: PauseControllerLike | None,
) -> str:
    """Compute quick signature for a file record using cache when available."""
    if cache is not None:
        return cache.get_or_compute_quick_signature(
            file.full_path,
            file.size_bytes,
            file.last_write_utc,
            cast(
                Callable[[], str],
                partial(
                    compute_quick_signature,
                    file.full_path,
                    cancel_event=cancel_event,
                    pause_controller=pause_controller,
                ),
            ),
        )
    return compute_quick_signature(
        file.full_path,
        cancel_event=cancel_event,
        pause_controller=pause_controller,
    )


def _split_similar_bucket(
    indices: list[int],
    image_hashes: list[tuple[FileRecord, int]],
    band_index: int,
) -> list[list[int]]:
    """Split very large similar-image buckets into deterministic sub-buckets."""
    if len(indices) <= SIMILAR_BUCKET_SIZE_LIMIT:
        return [indices]

    shift = ((band_index + 1) * SIMILAR_BAND_BITS) % SIMILAR_HASH_BITS
    mask = (1 << SIMILAR_SECONDARY_BITS) - 1
    secondary: dict[int, list[int]] = defaultdict(list)
    for idx in indices:
        value = image_hashes[idx][1]
        secondary[(value >> shift) & mask].append(idx)

    return [group for group in secondary.values() if len(group) > 1]


def compute_sha256(
    path: Path,
    *,
    cancel_event: threading.Event | None = None,
    pause_controller: PauseControllerLike | None = None,
) -> str:
    """Compute full SHA-256 digest for file content."""
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            _guard_cancel(cancel_event, pause_controller)
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def compute_quick_signature(
    path: Path,
    *,
    cancel_event: threading.Event | None = None,
    pause_controller: PauseControllerLike | None = None,
) -> str:
    """
    Fast content signature using a few slices of the file. Used only to filter candidates,
    never as the final truth (full SHA + exact compare is used for that).
    """
    size = path.stat().st_size
    if size <= 0:
        return "empty"

    offsets: list[tuple[int, int]] = []
    # first edge
    offsets.append((0, min(QUICK_EDGE_BYTES, size)))
    # middle samples
    if size > QUICK_EDGE_BYTES * 2:
        mid = size // 2
        start = max(0, mid - QUICK_MIDDLE_BYTES // 2)
        offsets.append((start, min(QUICK_MIDDLE_BYTES, size - start)))
    # last edge
    if size > QUICK_EDGE_BYTES:
        offsets.append((max(0, size - QUICK_EDGE_BYTES), min(QUICK_EDGE_BYTES, size)))

    h = hashlib.blake2b(digest_size=16)
    h.update(str(size).encode("utf-8"))

    with path.open("rb") as stream:
        for off, ln in offsets:
            _guard_cancel(cancel_event, pause_controller)
            stream.seek(off)
            chunk = stream.read(ln)
            h.update(chunk)

    return h.hexdigest().lower()


def split_exact_groups(
    files: list[FileRecord],
    *,
    cancel_event: threading.Event | None,
    pause_controller: PauseControllerLike | None = None,
) -> list[list[FileRecord]]:
    """
    Safety gate: split into groups where files are byte-identical.
    Protects against extremely rare cases (cache mismatch, silent corruption, etc.).
    """
    if len(files) < 2:
        return [files]

    groups: list[list[FileRecord]] = []
    remaining = list(files)
    while remaining:
        _guard_cancel(cancel_event, pause_controller)
        base = remaining[0]
        current = [base]
        next_remaining: list[FileRecord] = []
        for candidate in remaining[1:]:
            _guard_cancel(cancel_event, pause_controller)
            if candidate.size_bytes != base.size_bytes:
                next_remaining.append(candidate)
                continue
            if candidate.full_path == base.full_path:
                continue
            if files_equal(
                base.full_path,
                candidate.full_path,
                cancel_event=cancel_event,
                pause_controller=pause_controller,
            ):
                current.append(candidate)
            else:
                next_remaining.append(candidate)
        groups.append(current)
        remaining = next_remaining
    return groups


def files_equal(
    a: Path,
    b: Path,
    *,
    cancel_event: threading.Event | None = None,
    pause_controller: PauseControllerLike | None = None,
) -> bool:
    """
    Byte-by-byte equality check (streaming, low memory).
    """
    if a.stat().st_size != b.stat().st_size:
        return False

    buf = 1024 * 1024
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            _guard_cancel(cancel_event, pause_controller)
            ca = fa.read(buf)
            cb = fb.read(buf)
            if ca != cb:
                return False
            if not ca:
                return True


def compute_dhash(path: Path, size: int = 9) -> int:
    """
    dHash 64-bit perceptual hash.
    """
    if Image is None:
        raise RuntimeError("Pillow is not installed.")

    with Image.open(path) as raw_img:
        img = raw_img.convert("L").resize((size, size - 1))  # 9x8 -> 64 comparisons
        pixels = list(img.getdata())

    value = 0
    bit = 0
    for row in range(size - 1):
        for col in range(size - 1):
            left = pixels[row * size + col]
            right = pixels[row * size + col + 1]
            if left > right:
                value |= 1 << bit
            bit += 1
    return value


def hamming_distance(a: int, b: int) -> int:
    """Return bit distance between two 64-bit perceptual hashes."""
    return (a ^ b).bit_count()
