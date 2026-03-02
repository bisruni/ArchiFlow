from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable


class HashCacheService:
    def __init__(self, cache_path: Path) -> None:
        self._cache_path = cache_path
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, str | int]] | None = None

    def get_or_compute_sha256(
        self,
        path: Path,
        size_bytes: int,
        last_write_utc: datetime,
        compute_hash: Callable[[], str],
    ) -> str:
        key = self._make_key(path, size_bytes, last_write_utc)
        legacy_key = str(path.resolve()).lower()
        ticks = int(last_write_utc.timestamp() * 1_000_000)

        with self._lock:
            self._load_if_needed()
            assert self._cache is not None
            current = self._cache.get(key)
            if current and current.get("sha256"):
                return str(current["sha256"]).lower()
            legacy = self._cache.get(legacy_key)
            if legacy and legacy.get("size") == size_bytes and legacy.get("mtime") == ticks and legacy.get("sha256"):
                return str(legacy["sha256"]).lower()

        sha256_hash = compute_hash().lower()

        with self._lock:
            self._load_if_needed()
            assert self._cache is not None
            current = self._cache.get(key) or {}
            current["path"] = str(path.resolve())
            current["size"] = size_bytes
            current["mtime"] = ticks
            current["sha256"] = sha256_hash
            self._cache[key] = current
            self._save()

        return sha256_hash

    def get_or_compute_quick_signature(
        self,
        path: Path,
        size_bytes: int,
        last_write_utc: datetime,
        compute_signature: Callable[[], str],
    ) -> str:
        key = self._make_key(path, size_bytes, last_write_utc)
        legacy_key = str(path.resolve()).lower()
        ticks = int(last_write_utc.timestamp() * 1_000_000)

        with self._lock:
            self._load_if_needed()
            assert self._cache is not None
            current = self._cache.get(key)
            if current and current.get("quick_signature"):
                return str(current["quick_signature"]).lower()
            legacy = self._cache.get(legacy_key)
            if (
                legacy
                and legacy.get("size") == size_bytes
                and legacy.get("mtime") == ticks
                and legacy.get("quick_signature")
            ):
                return str(legacy["quick_signature"]).lower()

        quick_signature = compute_signature().lower()

        with self._lock:
            self._load_if_needed()
            assert self._cache is not None
            current = self._cache.get(key) or {}
            current["path"] = str(path.resolve())
            current["size"] = size_bytes
            current["mtime"] = ticks
            current["quick_signature"] = quick_signature
            self._cache[key] = current
            self._save()

        return quick_signature

    def _load_if_needed(self) -> None:
        if self._cache is not None:
            return

        if not self._cache_path.exists():
            self._cache = {}
            return

        try:
            with self._cache_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            self._cache = payload if isinstance(payload, dict) else {}
        except Exception:  # noqa: BLE001
            self._cache = {}

    def _save(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self._cache_path.open("w", encoding="utf-8") as stream:
            json.dump(self._cache or {}, stream, ensure_ascii=True, separators=(",", ":"))

    @staticmethod
    def _make_key(path: Path, size_bytes: int, last_write_utc: datetime) -> str:
        ticks = int(last_write_utc.timestamp() * 1_000_000)
        return f"{str(path.resolve()).lower()}|{size_bytes}|{ticks}"
