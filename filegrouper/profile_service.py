from __future__ import annotations

import json
import os
from pathlib import Path

from .models import DedupeMode, ExecutionScope, OperationProfile, OrganizationMode, ScanFilterOptions


class ProfileService:
    def __init__(self, profile_path: Path | None = None) -> None:
        self._profile_path = profile_path or default_profile_path()
        self._ensure_seed_profiles()

    def load_profiles(self) -> list[OperationProfile]:
        if not self._profile_path.exists():
            return self.seed_profiles()

        try:
            with self._profile_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if not isinstance(payload, list):
                return self.seed_profiles()
            return [OperationProfile.from_dict(item) for item in payload]
        except Exception:  # noqa: BLE001
            return self.seed_profiles()

    def save_profiles(self, profiles: list[OperationProfile]) -> None:
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [profile.to_dict() for profile in profiles]
        with self._profile_path.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=True, indent=2)

    def upsert_profile(self, profile: OperationProfile) -> None:
        profiles = self.load_profiles()
        by_name = {item.name.lower(): idx for idx, item in enumerate(profiles)}
        key = profile.name.lower()
        if key in by_name:
            profiles[by_name[key]] = profile
        else:
            profiles.append(profile)
        self.save_profiles(profiles)

    def _ensure_seed_profiles(self) -> None:
        if self._profile_path.exists():
            return
        self.save_profiles(self.seed_profiles())

    @staticmethod
    def seed_profiles() -> list[OperationProfile]:
        return [
            OperationProfile(
                name="Standard Safe",
                execution_scope=ExecutionScope.GROUP_AND_DEDUPE,
                organization_mode=OrganizationMode.COPY,
                dedupe_mode=DedupeMode.QUARANTINE,
                is_dry_run=True,
                detect_similar_images=False,
                filter_options=ScanFilterOptions(),
            ),
            OperationProfile(
                name="Photo Cleanup",
                execution_scope=ExecutionScope.GROUP_AND_DEDUPE,
                organization_mode=OrganizationMode.COPY,
                dedupe_mode=DedupeMode.QUARANTINE,
                is_dry_run=True,
                detect_similar_images=True,
                filter_options=ScanFilterOptions(include_extensions=[".jpg", ".jpeg", ".png", ".webp", ".heic"]),
            ),
            OperationProfile(
                name="Aggressive Move",
                execution_scope=ExecutionScope.GROUP_AND_DEDUPE,
                organization_mode=OrganizationMode.MOVE,
                dedupe_mode=DedupeMode.DELETE,
                is_dry_run=True,
                detect_similar_images=False,
                filter_options=ScanFilterOptions(),
            ),
        ]


def default_profile_path() -> Path:
    if os.name == "nt":
        root = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    elif sys_platform_is_macos():
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))

    legacy = root / "FileGrouper" / "profiles.json"
    if legacy.exists():
        return legacy
    return root / "ArchiFlow" / "profiles.json"


def sys_platform_is_macos() -> bool:
    return os.uname().sysname.lower() == "darwin" if hasattr(os, "uname") else False
