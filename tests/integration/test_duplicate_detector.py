from __future__ import annotations

import threading
from pathlib import Path

from archiflow.duplicate_detector import DuplicateDetector
from archiflow.hash_cache import HashCacheService
from archiflow.models import OperationStage
from archiflow.pause_controller import PauseController
from archiflow.scanner import FileScanner


def test_duplicate_detector_finds_only_exact_duplicates(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    (source / "a.bin").write_bytes(b"same-content")
    (source / "b.bin").write_bytes(b"same-content")
    (source / "c.bin").write_bytes(b"same-contenu")
    (source / "d.bin").write_bytes(b"unique")

    files = FileScanner().scan(source)
    detector = DuplicateDetector()
    cache = HashCacheService(tmp_path / ".archiflow" / "cache" / "hash-cache.json")

    stages: list[OperationStage] = []

    groups, similar = detector.find_duplicates(
        files,
        cache=cache,
        detect_similar_images=False,
        similar_max_distance=8,
        log=None,
        progress=lambda item: stages.append(item.stage),
        cancel_event=threading.Event(),
        pause_controller=PauseController(),
    )

    assert len(groups) == 1
    duplicate_names = {entry.full_path.name for entry in groups[0].files}
    assert duplicate_names == {"a.bin", "b.bin"}
    assert similar == []
    assert OperationStage.HASHING in stages
