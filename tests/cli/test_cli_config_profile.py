from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from archiflow import logger as logger_module
from archiflow.cli import main
from archiflow.config_service import AppConfig, AppConfigService
from archiflow.models import DedupeMode, ExecutionScope, OperationProfile, OrganizationMode, ScanFilterOptions
from archiflow.profile_service import ProfileService


@pytest.fixture(autouse=True)
def isolate_runtime_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCHIFLOW_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ARCHIFLOW_CONFIG_FILE", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("ARCHIFLOW_PROFILE_PATH", str(tmp_path / "profiles.json"))
    logger_module.reset_logging_state()
    logging.getLogger(logger_module.LOGGER_NAME).handlers.clear()


def test_cli_profiles_command_lists_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    profile_service = ProfileService(Path(tmp_path / "profiles.json"))
    profile_service.save_profiles(
        [
            OperationProfile(
                name="Custom",
                execution_scope=ExecutionScope.GROUP_ONLY,
                organization_mode=OrganizationMode.COPY,
                dedupe_mode=DedupeMode.QUARANTINE,
                is_dry_run=True,
                detect_similar_images=False,
                filter_options=ScanFilterOptions(),
            )
        ]
    )

    exit_code = main(["profiles", "--json"])
    output = capsys.readouterr().out

    assert exit_code == 0
    payload = json.loads(output)
    assert payload[0]["name"] == "Custom"


def test_cli_apply_uses_config_defaults_when_flags_missing(tmp_path: Path) -> None:
    AppConfigService(Path(tmp_path / "config.yaml")).save_config(
        AppConfig(
            default_scope=ExecutionScope.GROUP_ONLY,
            default_mode=OrganizationMode.MOVE,
            default_dedupe=DedupeMode.QUARANTINE,
            default_dry_run=True,
            default_similar_images=False,
        )
    )

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "doc.txt").write_text("data", encoding="utf-8")

    exit_code = main(["apply", "--source", str(source), "--target", str(target)])

    assert exit_code == 0
    assert (source / "doc.txt").exists()  # config default dry-run=True
    assert not any(target.rglob("doc.txt"))


def test_cli_apply_uses_selected_profile(tmp_path: Path) -> None:
    profile_service = ProfileService(Path(tmp_path / "profiles.json"))
    profile_service.save_profiles(
        [
            OperationProfile(
                name="MoveNow",
                execution_scope=ExecutionScope.GROUP_ONLY,
                organization_mode=OrganizationMode.MOVE,
                dedupe_mode=DedupeMode.QUARANTINE,
                is_dry_run=False,
                detect_similar_images=False,
                filter_options=ScanFilterOptions(),
            )
        ]
    )

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "doc.txt").write_text("data", encoding="utf-8")

    exit_code = main(
        [
            "apply",
            "--source",
            str(source),
            "--target",
            str(target),
            "--profile",
            "MoveNow",
        ]
    )

    assert exit_code == 0
    assert not (source / "doc.txt").exists()
    assert any(target.rglob("doc.txt"))
