"""Application configuration management via config.yaml + env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypeVar

from .constants import config_file_path
from .models import DedupeMode, ExecutionScope, OrganizationMode

EnumT = TypeVar("EnumT", bound=Enum)


@dataclass(slots=True)
class AppConfig:
    """Normalized application configuration values."""

    default_scope: ExecutionScope = ExecutionScope.GROUP_AND_DEDUPE
    default_mode: OrganizationMode = OrganizationMode.COPY
    default_dedupe: DedupeMode = DedupeMode.QUARANTINE
    default_dry_run: bool = False
    default_similar_images: bool = False
    default_profile: str = ""
    log_level: str = ""
    console_log_level: str = ""
    log_dir: Path | None = None

    def to_map(self) -> dict[str, str]:
        """Serialize config into flat YAML-compatible key/value map."""
        return {
            "default_scope": self.default_scope.value,
            "default_mode": self.default_mode.value,
            "default_dedupe": self.default_dedupe.value,
            "default_dry_run": "true" if self.default_dry_run else "false",
            "default_similar_images": "true" if self.default_similar_images else "false",
            "default_profile": self.default_profile,
            "log_level": self.log_level,
            "console_log_level": self.console_log_level,
            "log_dir": str(self.log_dir) if self.log_dir is not None else "",
        }

    @staticmethod
    def from_map(payload: dict[str, str]) -> "AppConfig":
        """Create AppConfig from parsed YAML payload with safe fallbacks."""
        scope = _parse_enum(
            ExecutionScope,
            payload.get("default_scope", ExecutionScope.GROUP_AND_DEDUPE.value),
            ExecutionScope.GROUP_AND_DEDUPE,
        )
        mode = _parse_enum(
            OrganizationMode,
            payload.get("default_mode", OrganizationMode.COPY.value),
            OrganizationMode.COPY,
        )
        dedupe = _parse_enum(
            DedupeMode,
            payload.get("default_dedupe", DedupeMode.QUARANTINE.value),
            DedupeMode.QUARANTINE,
        )
        return AppConfig(
            default_scope=scope,
            default_mode=mode,
            default_dedupe=dedupe,
            default_dry_run=_parse_bool(payload.get("default_dry_run"), False),
            default_similar_images=_parse_bool(payload.get("default_similar_images"), False),
            default_profile=payload.get("default_profile", "").strip(),
            log_level=payload.get("log_level", "").strip(),
            console_log_level=payload.get("console_log_level", "").strip(),
            log_dir=_parse_path(payload.get("log_dir")),
        )


class AppConfigService:
    """Load/save app config and resolve environment overrides."""

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize service with explicit/default config path."""
        self._config_path = config_path or default_config_path()
        self._ensure_seed_config()

    @property
    def config_path(self) -> Path:
        """Return active config file path."""
        return self._config_path

    def load_config(self) -> AppConfig:
        """Load config from disk; fallback to defaults if invalid."""
        if not self._config_path.exists():
            return AppConfig()
        try:
            payload = _parse_simple_yaml(self._config_path.read_text(encoding="utf-8"))
            return AppConfig.from_map(payload)
        except (OSError, IOError, ValueError):
            return AppConfig()

    def load_resolved_config(self) -> AppConfig:
        """Load config and apply environment variable overrides."""
        config = self.load_config()

        if "ARCHIFLOW_DEFAULT_SCOPE" in os.environ:
            config.default_scope = _parse_enum(
                ExecutionScope,
                os.environ.get("ARCHIFLOW_DEFAULT_SCOPE"),
                config.default_scope,
            )
        if "ARCHIFLOW_DEFAULT_MODE" in os.environ:
            config.default_mode = _parse_enum(
                OrganizationMode,
                os.environ.get("ARCHIFLOW_DEFAULT_MODE"),
                config.default_mode,
            )
        if "ARCHIFLOW_DEFAULT_DEDUPE" in os.environ:
            config.default_dedupe = _parse_enum(
                DedupeMode,
                os.environ.get("ARCHIFLOW_DEFAULT_DEDUPE"),
                config.default_dedupe,
            )
        if "ARCHIFLOW_DEFAULT_DRY_RUN" in os.environ:
            config.default_dry_run = _parse_bool(os.environ.get("ARCHIFLOW_DEFAULT_DRY_RUN"), config.default_dry_run)
        if "ARCHIFLOW_DEFAULT_SIMILAR_IMAGES" in os.environ:
            config.default_similar_images = _parse_bool(
                os.environ.get("ARCHIFLOW_DEFAULT_SIMILAR_IMAGES"),
                config.default_similar_images,
            )
        if "ARCHIFLOW_DEFAULT_PROFILE" in os.environ:
            config.default_profile = os.environ.get("ARCHIFLOW_DEFAULT_PROFILE", "").strip()

        if "ARCHIFLOW_LOG_LEVEL" in os.environ:
            config.log_level = os.environ.get("ARCHIFLOW_LOG_LEVEL", "").strip()
        if "ARCHIFLOW_CONSOLE_LOG_LEVEL" in os.environ:
            config.console_log_level = os.environ.get("ARCHIFLOW_CONSOLE_LOG_LEVEL", "").strip()
        if "ARCHIFLOW_LOG_DIR" in os.environ:
            config.log_dir = _parse_path(os.environ.get("ARCHIFLOW_LOG_DIR"))

        return config

    def save_config(self, config: AppConfig) -> None:
        """Persist config as human-readable YAML."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        content = _dump_simple_yaml(config.to_map())
        self._config_path.write_text(content, encoding="utf-8")

    def _ensure_seed_config(self) -> None:
        if self._config_path.exists():
            return
        self.save_config(AppConfig())


def default_config_path() -> Path:
    """Resolve default config path, honoring explicit env override."""
    env_path = os.environ.get("ARCHIFLOW_CONFIG_FILE", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return config_file_path(Path.cwd()).resolve()


def _parse_simple_yaml(content: str) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = value.strip()
        if "#" in normalized and not normalized.startswith(("'", '"')):
            normalized = normalized.split("#", 1)[0].strip()
        normalized = _strip_quotes(normalized)
        payload[key.strip()] = normalized
    return payload


def _dump_simple_yaml(payload: dict[str, str]) -> str:
    lines = [
        "# ArchiFlow configuration",
        "# You can override each value using ARCHIFLOW_* environment variables.",
        "",
    ]
    ordered_keys = [
        "default_scope",
        "default_mode",
        "default_dedupe",
        "default_dry_run",
        "default_similar_images",
        "default_profile",
        "log_level",
        "console_log_level",
        "log_dir",
    ]
    for key in ordered_keys:
        value = payload.get(key, "")
        lines.append(f"{key}: {value}")
    lines.append("")
    return "\n".join(lines)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_bool(value: str | None, fallback: bool) -> bool:
    if value is None:
        return fallback
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return fallback


def _parse_path(value: str | None) -> Path | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return Path(normalized).expanduser().resolve()


def _parse_enum(enum_type: type[EnumT], value: str | None, fallback: EnumT) -> EnumT:
    if value is None:
        return fallback
    try:
        return enum_type(value.strip().lower())
    except (ValueError, AttributeError):
        return fallback
