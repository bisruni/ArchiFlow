from __future__ import annotations

from pathlib import Path

import pytest

from archiflow.config_service import AppConfig, AppConfigService
from archiflow.models import DedupeMode, ExecutionScope, OrganizationMode


def test_config_service_creates_seed_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    service = AppConfigService(config_path)

    assert config_path.exists()
    loaded = service.load_config()
    assert loaded.default_scope is ExecutionScope.GROUP_AND_DEDUPE
    assert loaded.default_mode is OrganizationMode.COPY
    assert loaded.default_dedupe is DedupeMode.QUARANTINE
    assert loaded.default_dry_run is False


def test_config_service_load_resolved_config_applies_env_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    service = AppConfigService(config_path)
    service.save_config(
        AppConfig(
            default_scope=ExecutionScope.GROUP_ONLY,
            default_mode=OrganizationMode.MOVE,
            default_dedupe=DedupeMode.OFF,
            default_dry_run=False,
            default_similar_images=False,
            default_profile="Standard Safe",
            log_level="INFO",
        )
    )

    monkeypatch.setenv("ARCHIFLOW_DEFAULT_SCOPE", "dedupe_only")
    monkeypatch.setenv("ARCHIFLOW_DEFAULT_MODE", "copy")
    monkeypatch.setenv("ARCHIFLOW_DEFAULT_DRY_RUN", "true")
    monkeypatch.setenv("ARCHIFLOW_DEFAULT_SIMILAR_IMAGES", "yes")
    monkeypatch.setenv("ARCHIFLOW_DEFAULT_PROFILE", "Photo Cleanup")
    monkeypatch.setenv("ARCHIFLOW_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ARCHIFLOW_LOG_DIR", str(tmp_path / "logs"))

    resolved = service.load_resolved_config()
    assert resolved.default_scope is ExecutionScope.DEDUPE_ONLY
    assert resolved.default_mode is OrganizationMode.COPY
    assert resolved.default_dry_run is True
    assert resolved.default_similar_images is True
    assert resolved.default_profile == "Photo Cleanup"
    assert resolved.log_level == "DEBUG"
    assert resolved.log_dir == (tmp_path / "logs").resolve()


def test_config_service_invalid_values_fallback_to_safe_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "default_scope: not_a_scope",
                "default_mode: ???",
                "default_dedupe: ???",
                "default_dry_run: maybe",
                "default_similar_images: maybe",
            ]
        ),
        encoding="utf-8",
    )
    service = AppConfigService(config_path)
    loaded = service.load_config()

    assert loaded.default_scope is ExecutionScope.GROUP_AND_DEDUPE
    assert loaded.default_mode is OrganizationMode.COPY
    assert loaded.default_dedupe is DedupeMode.QUARANTINE
    assert loaded.default_dry_run is False
    assert loaded.default_similar_images is False
