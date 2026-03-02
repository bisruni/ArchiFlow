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
except Exception:
    Image = None

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


SUPPORTED_SIMILAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic"}

QUICK_EDGE_BYTES = 1024 * 1024
QUICK_MIDDLE_BYTES = 128 * 1024
SIMILAR_HASH_BITS = 64
SIMILAR_BAND_BITS = 16
SIMILAR_BAND_COUNT = SIMILAR_HASH_BITS // SIMILAR_BAND_BITS
SIMILAR_MAX_PAIRS = 2_000_000


class DuplicateDetector:
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
        grouped_by_size: dict[int, list[FileRecord]] = defaultdict(list)
        for file in files:
            grouped_by_size[file.size_bytes].append(file)

        size_candidates = [group for group in grouped_by_size.values() if len(group) > 1]
        quick_total = sum(len(group) for group in size_candidates)
        quick_processed = 0

        # Stage-1: quick signatures for cheap candidate filtering.
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
                except Exception as exc:  # noqa: BLE001
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

        # Stage-2: full SHA-256 only for filtered candidates.
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
                except Exception as exc:  # noqa: BLE001
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

            for sha256_hash, file_list in by_hash.items():
                if len(file_list) <= 1:
                    continue
                # Final safety gate: even with matching SHA/cache, only exact byte-equal files
                # are accepted into duplicate groups.
                exact_groups = split_exact_groups(file_list, cancel_event=cancel_event, pause_controller=pause_controller)
                for exact_group in exact_groups:
                    if len(exact_group) <= 1:
                        continue
                    ordered = sorted(exact_group, key=lambda item: (item.last_write_utc, str(item.full_path).lower()))
                    groups.append(DuplicateGroup(sha256_hash=sha256_hash, size_bytes=ordered[0].size_bytes, files=ordered))

        duplicate_groups = sorted(groups, key=lambda item: (-len(item.files), -item.size_bytes, item.sha256_hash))

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
            if log:
                log("Similar image detection skipped: Pillow is not installed.")
            return []

        # Compute real perceptual hashes (dHash) from decoded image pixels.
        image_hashes: list[tuple[FileRecord, int]] = []
        for index, item in enumerate(images, start=1):
            _guard_cancel(cancel_event, pause_controller)
            try:
                image_hashes.append((item, compute_dhash(item.full_path)))
            except Exception as exc:  # noqa: BLE001
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

        # Candidate generation with banding: avoid N^2 full pair scan.
        candidate_pairs, limited = build_similarity_candidate_pairs(image_hashes, max_pairs=SIMILAR_MAX_PAIRS)
        if limited and log:
            log(f"Similar image candidate pairs limited to {SIMILAR_MAX_PAIRS} for performance.")

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


def _guard_cancel(cancel_event: threading.Event | None, pause_controller) -> None:
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
    with path.open("rb") as stream:
        stream.seek(0, 2)
        length = stream.tell()
        if length <= 0:
            return "0"

        hasher = hashlib.blake2b(digest_size=16)
        hasher.update(length.to_bytes(8, byteorder="little", signed=False))

        edge = min(QUICK_EDGE_BYTES, length)
        mid = min(QUICK_MIDDLE_BYTES, length)

        stream.seek(0)
        hasher.update(stream.read(edge))

        if length > edge:
            stream.seek(max(0, length - edge))
            hasher.update(stream.read(edge))

        middle_offsets = {max(0, length // 2 - mid // 2), max(0, length // 3 - mid // 2), max(0, (2 * length) // 3 - mid // 2)}
        for offset in sorted(middle_offsets):
            stream.seek(offset)
            hasher.update(stream.read(mid))

    return hasher.hexdigest().lower()


def compute_dhash(path: Path, size: int = 8) -> int:
    if Image is None:
        raise RuntimeError("Pillow is required for image hashing.")

    with Image.open(path) as image:
        if hasattr(Image, "Resampling"):
            resample = Image.Resampling.LANCZOS
        else:
            resample = Image.LANCZOS
        resized = image.convert("L").resize((size + 1, size), resample)
        pixels = list(resized.getdata())

    value = 0
    row_width = size + 1
    for y in range(size):
        row_offset = y * row_width
        for x in range(size):
            left = pixels[row_offset + x]
            right = pixels[row_offset + x + 1]
            value = (value << 1) | (1 if left > right else 0)
    return value


def build_similarity_candidate_pairs(
    items: list[tuple[FileRecord, int]],
    *,
    max_pairs: int,
) -> tuple[list[tuple[int, int]], bool]:
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, (_, image_hash) in enumerate(items):
        for band_index in range(SIMILAR_BAND_COUNT):
            shift = band_index * SIMILAR_BAND_BITS
            band_value = (image_hash >> shift) & ((1 << SIMILAR_BAND_BITS) - 1)
            buckets[(band_index, band_value)].append(idx)

    pairs: set[tuple[int, int]] = set()
    limited = False
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for left_idx in range(len(bucket)):
            a = bucket[left_idx]
            for right_idx in range(left_idx + 1, len(bucket)):
                b = bucket[right_idx]
                if a < b:
                    pairs.add((a, b))
                else:
                    pairs.add((b, a))
                if len(pairs) >= max_pairs:
                    limited = True
                    return list(pairs), limited

    return list(pairs), limited


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def split_exact_groups(
    files: list[FileRecord],
    *,
    cancel_event: threading.Event | None,
    pause_controller,
) -> list[list[FileRecord]]:
    groups: list[list[FileRecord]] = []
    for file in files:
        _guard_cancel(cancel_event, pause_controller)
        placed = False
        for group in groups:
            if are_files_byte_equal(file.full_path, group[0].full_path):
                group.append(file)
                placed = True
                break
        if not placed:
            groups.append([file])
    return groups


def are_files_byte_equal(left: Path, right: Path) -> bool:
    try:
        if left == right:
            return True
        if left.stat().st_size != right.stat().st_size:
            return False

        buf_size = 1024 * 1024
        with left.open("rb") as ls, right.open("rb") as rs:
            while True:
                lb = ls.read(buf_size)
                rb = rs.read(buf_size)
                if lb != rb:
                    return False
                if not lb:
                    return True
    except OSError:
        return False
