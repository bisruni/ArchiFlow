from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from archiflow.hash_cache import HashCacheService


def _last_write_utc(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def test_hash_cache_reuses_cached_sha256(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha", encoding="utf-8")
    cache = HashCacheService(tmp_path / ".archiflow" / "cache" / "hash-cache.json")

    calls = 0

    def compute_hash() -> str:
        nonlocal calls
        calls += 1
        return "ABCDEF"

    first = cache.get_or_compute_sha256(
        file_path,
        file_path.stat().st_size,
        _last_write_utc(file_path),
        compute_hash,
    )
    second = cache.get_or_compute_sha256(
        file_path,
        file_path.stat().st_size,
        _last_write_utc(file_path),
        compute_hash,
    )

    assert first == "abcdef"
    assert second == "abcdef"
    assert calls == 1


def test_hash_cache_invalidates_when_size_or_mtime_changes(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha", encoding="utf-8")
    cache = HashCacheService(tmp_path / ".archiflow" / "cache" / "hash-cache.json")

    calls = 0

    def compute_hash() -> str:
        nonlocal calls
        calls += 1
        return f"hash-{calls}"

    first = cache.get_or_compute_sha256(
        file_path,
        file_path.stat().st_size,
        _last_write_utc(file_path),
        compute_hash,
    )

    file_path.write_text("alpha-beta", encoding="utf-8")
    second = cache.get_or_compute_sha256(
        file_path,
        file_path.stat().st_size,
        _last_write_utc(file_path),
        compute_hash,
    )
    cache.flush()

    assert first == "hash-1"
    assert second == "hash-2"
    assert calls == 2
    payload = json.loads((tmp_path / ".archiflow" / "cache" / "hash-cache.json").read_text(encoding="utf-8"))
    assert len(payload) == 1
    assert cache.get_stats()["invalidations"] >= 1


def test_hash_cache_supports_legacy_key_format(tmp_path: Path) -> None:
    file_path = tmp_path / "legacy.bin"
    file_path.write_bytes(b"legacy")
    snapshot = _last_write_utc(file_path)
    ticks = int(snapshot.timestamp() * 1_000_000)

    cache_path = tmp_path / ".archiflow" / "cache" / "hash-cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_key = str(file_path.resolve()).lower()
    cache_path.write_text(
        ("{" f'"{legacy_key}":{{"size":{file_path.stat().st_size},"mtime":{ticks},"sha256":"LEGACYHASH"}}' "}"),
        encoding="utf-8",
    )

    cache = HashCacheService(cache_path)
    value = cache.get_or_compute_sha256(
        file_path,
        file_path.stat().st_size,
        snapshot,
        lambda: "SHOULD_NOT_RUN",
    )

    assert value == "legacyhash"


def test_hash_cache_thread_safe_single_compute_for_same_sha(tmp_path: Path) -> None:
    file_path = tmp_path / "race.bin"
    file_path.write_bytes(b"thread-safe-test")
    cache = HashCacheService(tmp_path / ".archiflow" / "cache" / "hash-cache.json")

    start_event = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def compute_hash() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.01)
        return "THREADHASH"

    def worker() -> str:
        start_event.wait()
        return cache.get_or_compute_sha256(
            file_path,
            file_path.stat().st_size,
            _last_write_utc(file_path),
            compute_hash,
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(worker) for _ in range(64)]
        start_event.set()
        results = [future.result() for future in futures]

    assert set(results) == {"threadhash"}
    assert calls == 1


def test_hash_cache_thread_safe_single_compute_for_quick_signature(tmp_path: Path) -> None:
    file_path = tmp_path / "quick-race.bin"
    file_path.write_bytes(b"quick-thread-safe-test")
    cache = HashCacheService(tmp_path / ".archiflow" / "cache" / "hash-cache.json")

    start_event = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def compute_signature() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.01)
        return "QUICKSIG"

    def worker() -> str:
        start_event.wait()
        return cache.get_or_compute_quick_signature(
            file_path,
            file_path.stat().st_size,
            _last_write_utc(file_path),
            compute_signature,
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(worker) for _ in range(64)]
        start_event.set()
        results = [future.result() for future in futures]

    assert set(results) == {"quicksig"}
    assert calls == 1


def test_hash_cache_stress_parallel_reads_writes_produce_valid_json(tmp_path: Path) -> None:
    source_dir = tmp_path / "stress"
    source_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for index in range(40):
        item = source_dir / f"f-{index:03d}.dat"
        item.write_bytes(f"payload-{index}".encode("utf-8"))
        files.append(item)

    cache_path = tmp_path / ".archiflow" / "cache" / "hash-cache.json"
    cache = HashCacheService(cache_path)
    start_event = threading.Event()

    def worker(index: int) -> str:
        start_event.wait()
        file_path = files[index % len(files)]
        if index % 2 == 0:
            return cache.get_or_compute_sha256(
                file_path,
                file_path.stat().st_size,
                _last_write_utc(file_path),
                lambda item=file_path: f"sha-{item.name}",
            )
        return cache.get_or_compute_quick_signature(
            file_path,
            file_path.stat().st_size,
            _last_write_utc(file_path),
            lambda item=file_path: f"quick-{item.name}",
        )

    with ThreadPoolExecutor(max_workers=24) as executor:
        futures = [executor.submit(worker, i) for i in range(800)]
        start_event.set()
        results = [future.result() for future in futures]

    cache.flush()

    assert results
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert len(payload) >= len(files)


def test_hash_cache_lru_eviction_keeps_recent_entries(tmp_path: Path) -> None:
    cache_path = tmp_path / ".archiflow" / "cache" / "hash-cache.json"
    cache = HashCacheService(cache_path, max_entries=2)
    files = [tmp_path / f"lru-{idx}.txt" for idx in range(3)]
    for idx, item in enumerate(files):
        item.write_text(f"payload-{idx}", encoding="utf-8")

    cache.get_or_compute_sha256(files[0], files[0].stat().st_size, _last_write_utc(files[0]), lambda: "A")
    cache.get_or_compute_sha256(files[1], files[1].stat().st_size, _last_write_utc(files[1]), lambda: "B")
    cache.get_or_compute_sha256(files[0], files[0].stat().st_size, _last_write_utc(files[0]), lambda: "A2")
    cache.get_or_compute_sha256(files[2], files[2].stat().st_size, _last_write_utc(files[2]), lambda: "C")
    cache.flush()

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    payload_text = json.dumps(payload)
    assert str(files[0].resolve()).lower() in payload_text
    assert str(files[2].resolve()).lower() in payload_text
    assert cache.get_stats()["evictions"] >= 1


def test_hash_cache_exposes_hit_miss_stats(tmp_path: Path) -> None:
    file_path = tmp_path / "stats.txt"
    file_path.write_text("stats", encoding="utf-8")
    cache = HashCacheService(tmp_path / ".archiflow" / "cache" / "hash-cache.json", max_entries=10)

    cache.get_or_compute_sha256(file_path, file_path.stat().st_size, _last_write_utc(file_path), lambda: "STAT")
    cache.get_or_compute_sha256(file_path, file_path.stat().st_size, _last_write_utc(file_path), lambda: "STAT2")
    stats = cache.get_stats()

    assert stats["misses"] == 1
    assert stats["hits"] >= 1
    assert stats["computes"] == 1
    assert stats["entries"] == 1
    assert stats["lock_acquires"] >= 1
    assert stats["lock_wait_ns"] >= 0
