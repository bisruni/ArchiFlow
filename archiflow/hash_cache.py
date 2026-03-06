"""Persistent hash cache with rate-limited disk flush semantics."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator


class HashCacheService:
    """Store and reuse expensive file hashes keyed by path/size/mtime."""

    def __init__(self, cache_path: Path, *, max_entries: int = 200_000) -> None:
        """Initialize cache service bound to given JSON cache path.

        Args:
            cache_path: Cache file path.
            max_entries: Maximum in-memory/persisted entries before LRU eviction.
        """
        self._cache_path = cache_path
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, str | int]] | None = None
        self._path_index: dict[str, set[str]] = defaultdict(set)
        self._access_order: dict[str, int] = {}
        self._access_counter = 0
        self._inflight: dict[tuple[str, str], threading.Event] = {}
        self._dirty = False
        self._updates_since_save = 0
        self._last_save_monotonic = 0.0
        self._save_update_threshold = 50
        self._save_interval_seconds = 1.0
        self._stats: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "waits": 0,
            "computes": 0,
            "writes": 0,
            "evictions": 0,
            "invalidations": 0,
            "lock_acquires": 0,
            "lock_wait_ns": 0,
        }

    def get_or_compute_sha256(
        self,
        path: Path,
        size_bytes: int,
        last_write_utc: datetime,
        compute_hash: Callable[[], str],
    ) -> str:
        """Return cached SHA-256 or compute/update it for a file snapshot.

        Args:
            path: File path.
            size_bytes: File size in bytes.
            last_write_utc: File last modified timestamp.
            compute_hash: Callback used when cache miss occurs.

        Returns:
            str: Lower-cased SHA-256 value.
        """
        return self._get_or_compute_value(
            path=path,
            size_bytes=size_bytes,
            last_write_utc=last_write_utc,
            value_field="sha256",
            compute_value=compute_hash,
        )

    def get_or_compute_quick_signature(
        self,
        path: Path,
        size_bytes: int,
        last_write_utc: datetime,
        compute_signature: Callable[[], str],
    ) -> str:
        """Return cached quick signature or compute/update it for a file snapshot.

        Args:
            path: File path.
            size_bytes: File size in bytes.
            last_write_utc: File last modified timestamp.
            compute_signature: Callback used when cache miss occurs.

        Returns:
            str: Lower-cased quick signature value.
        """
        return self._get_or_compute_value(
            path=path,
            size_bytes=size_bytes,
            last_write_utc=last_write_utc,
            value_field="quick_signature",
            compute_value=compute_signature,
        )

    def flush(self) -> None:
        """Persist pending cache updates to disk when dirty.

        Returns:
            None

        Example:
            >>> # cache.flush()
            >>> # Ensures buffered cache updates are written to disk.
        """
        with self._locked():
            self._save(force=False)

    def get_stats(self) -> dict[str, int]:
        """Return current cache stats snapshot including active entry count."""
        with self._locked():
            self._load_if_needed()
            assert self._cache is not None
            stats = dict(self._stats)
            stats["entries"] = len(self._cache)
            stats["max_entries"] = self._max_entries
            stats["inflight"] = len(self._inflight)
            return stats

    def _load_if_needed(self) -> None:
        if self._cache is not None:
            return

        if not self._cache_path.exists():
            self._cache = {}
            return

        try:
            with self._cache_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if isinstance(payload, dict):
                parsed: dict[str, dict[str, str | int]] = {}
                for key, value in payload.items():
                    if isinstance(key, str) and isinstance(value, dict):
                        parsed[key] = value
                self._cache = parsed
            else:
                self._cache = {}
        except (OSError, IOError, json.JSONDecodeError):  # File I/O or invalid JSON
            self._cache = {}

        self._rebuild_indexes_unlocked()

    def _mark_dirty_and_maybe_save(self) -> None:
        self._dirty = True
        self._updates_since_save += 1
        now = time.monotonic()
        if (
            self._updates_since_save >= self._save_update_threshold
            or (now - self._last_save_monotonic) >= self._save_interval_seconds
        ):
            self._save(force=True)

    def _get_or_compute_value(
        self,
        *,
        path: Path,
        size_bytes: int,
        last_write_utc: datetime,
        value_field: str,
        compute_value: Callable[[], str],
    ) -> str:
        key = self._make_key(path, size_bytes, last_write_utc)
        path_norm = str(path.resolve()).lower()
        legacy_key = path_norm
        ticks = int(last_write_utc.timestamp() * 1_000_000)
        inflight_key = (value_field, key)

        while True:
            with self._locked():
                self._load_if_needed()
                assert self._cache is not None
                cached = self._read_cached_value_unlocked(
                    key=key,
                    legacy_key=legacy_key,
                    size_bytes=size_bytes,
                    ticks=ticks,
                    value_field=value_field,
                )
                if cached is not None:
                    self._stats["hits"] += 1
                    return cached

                wait_event = self._inflight.get(inflight_key)
                if wait_event is None:
                    self._stats["misses"] += 1
                    wait_event = threading.Event()
                    self._inflight[inflight_key] = wait_event
                    break
                self._stats["waits"] += 1

            wait_event.wait()

        try:
            computed = compute_value().lower()
            self._stats["computes"] += 1

            with self._locked():
                self._load_if_needed()
                assert self._cache is not None
                cached = self._read_cached_value_unlocked(
                    key=key,
                    legacy_key=legacy_key,
                    size_bytes=size_bytes,
                    ticks=ticks,
                    value_field=value_field,
                )
                if cached is not None:
                    self._stats["hits"] += 1
                    return cached

                current = self._cache.get(key) or {}
                current["path"] = path_norm
                current["size"] = size_bytes
                current["mtime"] = ticks
                current[value_field] = computed
                self._cache[key] = current
                self._register_key_for_path_unlocked(path_norm, key)
                self._touch_key_unlocked(key)
                self._invalidate_old_versions_unlocked(path_norm, keep_key=key)
                self._evict_lru_unlocked()
                self._mark_dirty_and_maybe_save()
                return computed
        finally:
            with self._locked():
                done_event = self._inflight.pop(inflight_key, None)
                if done_event is not None:
                    done_event.set()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        start = time.perf_counter_ns()
        self._lock.acquire()
        waited = time.perf_counter_ns() - start
        self._stats["lock_acquires"] += 1
        self._stats["lock_wait_ns"] += waited
        try:
            yield
        finally:
            self._lock.release()

    def _read_cached_value_unlocked(
        self,
        *,
        key: str,
        legacy_key: str,
        size_bytes: int,
        ticks: int,
        value_field: str,
    ) -> str | None:
        assert self._cache is not None

        current = self._cache.get(key)
        if current and current.get(value_field):
            self._touch_key_unlocked(key)
            return str(current[value_field]).lower()

        legacy = self._cache.get(legacy_key)
        if legacy and legacy.get("size") == size_bytes and legacy.get("mtime") == ticks and legacy.get(value_field):
            self._touch_key_unlocked(legacy_key)
            return str(legacy[value_field]).lower()

        return None

    def _save(self, *, force: bool) -> None:
        if not force and not self._dirty:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._cache_path.with_name(f".{self._cache_path.name}.tmp")
        with temp_path.open("w", encoding="utf-8") as stream:
            json.dump(self._cache or {}, stream, ensure_ascii=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, self._cache_path)
        self._stats["writes"] += 1
        self._dirty = False
        self._updates_since_save = 0
        self._last_save_monotonic = time.monotonic()

    @staticmethod
    def _make_key(path: Path, size_bytes: int, last_write_utc: datetime) -> str:
        ticks = int(last_write_utc.timestamp() * 1_000_000)
        return f"{str(path.resolve()).lower()}|{size_bytes}|{ticks}"

    def _rebuild_indexes_unlocked(self) -> None:
        assert self._cache is not None
        self._path_index.clear()
        self._access_order.clear()
        self._access_counter = 0
        for key, value in self._cache.items():
            path_norm = str(value.get("path", self._path_from_key(key))).lower()
            self._register_key_for_path_unlocked(path_norm, key)
            self._touch_key_unlocked(key)

    def _register_key_for_path_unlocked(self, path_norm: str, key: str) -> None:
        self._path_index[path_norm].add(key)

    def _unregister_key_for_path_unlocked(self, key: str) -> None:
        assert self._cache is not None
        value = self._cache.get(key)
        if value is None:
            return
        path_norm = str(value.get("path", self._path_from_key(key))).lower()
        key_set = self._path_index.get(path_norm)
        if key_set is None:
            return
        key_set.discard(key)
        if not key_set:
            self._path_index.pop(path_norm, None)

    def _touch_key_unlocked(self, key: str) -> None:
        self._access_counter += 1
        self._access_order[key] = self._access_counter

    def _invalidate_old_versions_unlocked(self, path_norm: str, *, keep_key: str) -> None:
        assert self._cache is not None
        versions = list(self._path_index.get(path_norm, set()))
        for old_key in versions:
            if old_key == keep_key:
                continue
            if old_key in self._cache:
                self._remove_key_unlocked(old_key, reason="invalidation")

    def _evict_lru_unlocked(self) -> None:
        assert self._cache is not None
        if self._max_entries <= 0:
            return
        while len(self._cache) > self._max_entries:
            lru_key = min(self._access_order, key=self._access_order.__getitem__, default=None)
            if lru_key is None:
                break
            self._remove_key_unlocked(lru_key, reason="eviction")

    def _remove_key_unlocked(self, key: str, *, reason: str) -> None:
        assert self._cache is not None
        if key not in self._cache:
            return
        self._unregister_key_for_path_unlocked(key)
        self._cache.pop(key, None)
        self._access_order.pop(key, None)
        if reason == "eviction":
            self._stats["evictions"] += 1
        elif reason == "invalidation":
            self._stats["invalidations"] += 1

    @staticmethod
    def _path_from_key(key: str) -> str:
        if "|" not in key:
            return key
        return key.split("|", 1)[0]
