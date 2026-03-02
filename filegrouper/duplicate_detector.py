from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .hash_cache import HashCacheService
from .models import DuplicateGroup, FileRecord, OperationProgress, OperationStage, SimilarImageGroup

LogFn = Callable[[str], None]
ProgressFn = Callable[[OperationProgress], None]


SUPPORTED_SIMILAR_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic"}


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

        groups: list[DuplicateGroup] = []
        hashed_count = 0

        for size, size_group in grouped_by_size.items():
            if len(size_group) < 2:
                continue

            by_hash: dict[str, list[FileRecord]] = defaultdict(list)
            for file in size_group:
                if cancel_event is not None and cancel_event.is_set():
                    raise OperationCancelledError()
                if pause_controller is not None:
                    pause_controller.wait_if_paused(cancel_event)

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
                hashed_count += 1
                if progress and hashed_count % 100 == 0:
                    progress(
                        OperationProgress(
                            stage=OperationStage.HASHING,
                            processed_files=hashed_count,
                            total_files=len(files),
                            message="Computing hashes",
                        )
                    )

            for sha256_hash, file_list in by_hash.items():
                if len(file_list) <= 1:
                    continue
                ordered = sorted(file_list, key=lambda item: (item.last_write_utc, str(item.full_path).lower()))
                groups.append(DuplicateGroup(sha256_hash=sha256_hash, size_bytes=size, files=ordered))

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

        fingerprints: list[tuple[FileRecord, int]] = []
        for index, item in enumerate(images, start=1):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)

            try:
                fingerprints.append((item, compute_byte_fingerprint(item.full_path)))
            except Exception as exc:  # noqa: BLE001
                if log:
                    log(f"Could not compute similarity fingerprint for '{item.full_path}': {exc}")

            if progress:
                progress(
                    OperationProgress(
                        stage=OperationStage.SIMILARITY,
                        processed_files=index,
                        total_files=len(images),
                        message="Computing similarity fingerprints",
                    )
                )

        if len(fingerprints) < 2:
            return []

        parent = list(range(len(fingerprints)))
        rank = [0] * len(fingerprints)

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

        for i in range(len(fingerprints)):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelledError()
            if pause_controller is not None:
                pause_controller.wait_if_paused(cancel_event)

            for j in range(i + 1, len(fingerprints)):
                a_size = fingerprints[i][0].size_bytes
                b_size = fingerprints[j][0].size_bytes
                ratio = min(a_size, b_size) / max(a_size, b_size) if a_size and b_size else 0.0
                if ratio < 0.7:
                    continue
                distance = hamming_distance(fingerprints[i][1], fingerprints[j][1])
                if distance <= max_distance:
                    union(i, j)

        groups_index: dict[int, list[FileRecord]] = defaultdict(list)
        for idx, (item, _) in enumerate(fingerprints):
            groups_index[find(idx)].append(item)

        similar_groups: list[SimilarImageGroup] = []
        for items in groups_index.values():
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


class OperationCancelledError(RuntimeError):
    pass


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def compute_byte_fingerprint(path: Path) -> int:
    with path.open("rb") as stream:
        stream.seek(0, 2)
        length = stream.tell()
        if length <= 0:
            return 0

        offsets = [
            0,
            max(0, length // 4 - 8),
            max(0, length // 2 - 8),
            max(0, (length * 3) // 4 - 8),
            max(0, length - 16),
        ]

        sample = bytearray()
        for offset in offsets:
            stream.seek(offset)
            sample.extend(stream.read(12))
            if len(sample) >= 64:
                sample = sample[:64]
                break

    fingerprint = 1469598103934665603
    for value in sample:
        fingerprint ^= value
        fingerprint = (fingerprint * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()
