from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .errors import OperationCancelledError
from .hash_cache import HashCacheService
from .models import DuplicateGroup, FileRecord, OperationProgress, OperationStage, SimilarImageGroup

try:
    from PIL import Image  # type: ignore
except ImportError:
    Image = None

try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except ImportError:
    pass

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


SUPPORTED_SIMILAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic"}

# Quick signature reads a few slices of the file (fast). Used as stage-1 filter before full SHA.
QUICK_EDGE_BYTES = 1024 * 1024     # first/last 1MB
QUICK_MIDDLE_BYTES = 128 * 1024    # 128KB samples in middle

# Similar image: dHash(64-bit) + banding candidate generation (avoid N^2).
SIMILAR_HASH_BITS = 64
SIMILAR_BAND_BITS = 16
SIMILAR_BAND_COUNT = SIMILAR_HASH_BITS // SIMILAR_BAND_BITS
SIMILAR_MAX_PAIRS = 2_000_000  # hard cap to avoid runaway on huge libraries


class DuplicateDetector:
    def __init__(self) -> None:
        """Initialize DuplicateDetector with instance state.
        
        Tracks whether Pillow unavailability warning has been logged
        to avoid duplicate log messages.
        """
        self._similar_unavailable_logged = False

    @staticmethod
    def is_similar_supported() -> bool:
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
        pause_controller=None,
    ) -> tuple[list[DuplicateGroup], list[SimilarImageGroup]]:
        # 1) group by size (cheap)
        grouped_by_size: dict[int, list[FileRecord]] = defaultdict(list)
        for file in files:
            grouped_by_size[file.size_bytes].append(file)

        size_candidates = [group for group in grouped_by_size.values() if len(group) > 1]

        # 2) stage-1 quick signature (fast IO) to reduce candidates
        quick_total = sum(len(group) for group in size_candidates)
        quick_processed = 0

        hash_input_groups: list[list[FileRecord]] = []
        for size_group in size_candidates:
            by_quick: dict[str, list[FileRecord]] = defaultdict(list)
            for file in size_group:
                _guard_cancel(cancel_event, pause_controller)

                try:
                    if cache is not None:
                        quick_signature = cache.get_or_compute_quick_signature(
                            file.full_path,
                            file.size_bytes,
                            file.last_write_utc,
                            lambda fp=file.full_path: compute_quick_signature(fp),
                        )
                    else:
                        quick_signature = compute_quick_signature(file.full_path)
                except (OSError, IOError, ValueError) as exc:  # File I/O or hash computation
                    if log:
                        log(f"Could not compute quick signature for '{file.full_path}': {exc}")
                    continue

                by_quick[quick_signature].append(file)
                quick_processed += 1
                if progress and (quick_processed % 200 == 0 or quick_processed == quick_total):
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

        # 3) stage-2 full SHA only on filtered candidates
        groups: list[DuplicateGroup] = []
        full_total = sum(len(group) for group in hash_input_groups)
        full_processed = 0

        for candidate_group in hash_input_groups:
            by_hash: dict[str, list[FileRecord]] = defaultdict(list)
            for file in candidate_group:
                _guard_cancel(cancel_event, pause_controller)

                try:
                    if cache is not None:
                        sha256_hash = cache.get_or_compute_sha256(
                            file.full_path,
                            file.size_bytes,
                            file.last_write_utc,
                            lambda fp=file.full_path: compute_sha256(fp),
                        )
                    else:
                        sha256_hash = compute_sha256(file.full_path)
                except (OSError, IOError, ValueError) as exc:  # File I/O or hash computation
                    if log:
                        log(f"Could not hash '{file.full_path}': {exc}")
                    continue

                by_hash[sha256_hash].append(file)
                full_processed += 1
                if progress and (full_processed % 100 == 0 or full_processed == full_total):
                    progress(
                        OperationProgress(
                            stage=OperationStage.HASHING,
                            processed_files=full_processed,
                            total_files=max(full_total, 1),
                            message="Computing full hashes",
                        )
                    )

            # 4) final safety: even if SHA matches, verify byte-identical to avoid any edge-case corruption/cache bugs
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
                    ordered = sorted(exact_group, key=lambda item: (item.last_write_utc, str(item.full_path).lower()))
                    groups.append(
                        DuplicateGroup(
                            sha256_hash=sha256_hash,
                            size_bytes=ordered[0].size_bytes,
                            files=ordered,
                        )
                    )

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
        pause_controller=None,
    ) -> list[SimilarImageGroup]:
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
                if log:
                    log(f"Could not compute image hash for '{item.full_path}': {exc}")

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

        # 2) candidate generation with banding (avoid N^2)
        candidate_pairs, limited = build_similarity_candidate_pairs(image_hashes, max_pairs=SIMILAR_MAX_PAIRS)
        if limited and log:
            log(f"Similar image candidate pairs limited to {SIMILAR_MAX_PAIRS} for performance.")

        # 3) union-find clustering by hamming distance
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

        total_pairs = len(candidate_pairs)
        for index, (a_idx, b_idx) in enumerate(candidate_pairs, start=1):
            _guard_cancel(cancel_event, pause_controller)

            a_hash = image_hashes[a_idx][1]
            b_hash = image_hashes[b_idx][1]
            if hamming_distance(a_hash, b_hash) <= max_distance:
                union(a_idx, b_idx)

            if progress and (index % 2000 == 0 or index == total_pairs):
                progress(
                    OperationProgress(
                        stage=OperationStage.SIMILARITY,
                        processed_files=index,
                        total_files=max(total_pairs, 1),
                        message="Comparing similar images",
                    )
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


def _guard_cancel(cancel_event: threading.Event | None, pause_controller=None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelledError()
    if pause_controller is not None:
        pause_controller.wait_if_paused(cancel_event)


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def compute_quick_signature(path: Path) -> str:
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
            stream.seek(off)
            chunk = stream.read(ln)
            h.update(chunk)

    return h.hexdigest().lower()


def split_exact_groups(
    files: list[FileRecord],
    *,
    cancel_event: threading.Event | None,
    pause_controller=None,
) -> list[list[FileRecord]]:
    """
    Safety gate: split into groups where files are byte-identical.
    Protects against extremely rare cases (cache mismatch, silent corruption, etc.).
    """
    if len(files) < 2:
        return [files]

    groups: list[list[FileRecord]] = []
    used = [False] * len(files)

    for i in range(len(files)):
        _guard_cancel(cancel_event, pause_controller)
        if used[i]:
            continue
        base = files[i]
        bucket = [base]
        used[i] = True

        for j in range(i + 1, len(files)):
            _guard_cancel(cancel_event, pause_controller)
            if used[j]:
                continue
            if files[j].size_bytes != base.size_bytes:
                continue
            if files[j].full_path == base.full_path:
                continue
            if files_equal(base.full_path, files[j].full_path):
                bucket.append(files[j])
                used[j] = True

        groups.append(bucket)

    return groups


def files_equal(a: Path, b: Path) -> bool:
    """
    Byte-by-byte equality check (streaming, low memory).
    """
    if a.stat().st_size != b.stat().st_size:
        return False

    buf = 1024 * 1024
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
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
    img = Image.open(path)  # type: ignore[union-attr]
    img = img.convert("L").resize((size, size - 1))  # 9x8 -> 64 comparisons
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


def build_similarity_candidate_pairs(
    image_hashes: list[tuple[FileRecord, int]],
    *,
    max_pairs: int,
) -> tuple[list[tuple[int, int]], bool]:
    """
    Banding: split 64-bit hash into 4x16-bit bands.
    Files that share any band are considered candidate pairs.
    """
    buckets: list[dict[int, list[int]]] = [defaultdict(list) for _ in range(SIMILAR_BAND_COUNT)]
    for idx, (_, h) in enumerate(image_hashes):
        for b in range(SIMILAR_BAND_COUNT):
            shift = b * SIMILAR_BAND_BITS
            band = (h >> shift) & ((1 << SIMILAR_BAND_BITS) - 1)
            buckets[b][band].append(idx)

    seen: set[tuple[int, int]] = set()
    pairs: list[tuple[int, int]] = []
    limited = False

    for bucket_map in buckets:
        for indices in bucket_map.values():
            if len(indices) < 2:
                continue
            indices = sorted(indices)
            for i in range(len(indices)):
                for j in range(i + 1, len(indices)):
                    a, b = indices[i], indices[j]
                    key = (a, b)
                    if key in seen:
                        continue
                    seen.add(key)
                    pairs.append(key)
                    if len(pairs) >= max_pairs:
                        limited = True
                        return pairs, limited

    return pairs, limited


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()
