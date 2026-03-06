from __future__ import annotations

from pathlib import Path

import pytest

from archiflow.errors import ValidationError
from archiflow.models import DedupeMode, ExecutionScope, OrganizationMode
from archiflow.validators import (
    validate_dedupe_mode,
    validate_organization_mode,
    validate_paths,
    validate_scope,
    validate_source_path,
    validate_target_path,
)


def test_validate_source_path_success(tmp_path: Path) -> None:
    assert validate_source_path(str(tmp_path)) == tmp_path.resolve()


def test_validate_source_path_missing() -> None:
    with pytest.raises(ValidationError):
        validate_source_path(None)


def test_validate_source_path_not_found(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        validate_source_path(str(tmp_path / "not-found"))


def test_validate_target_path_grouping_allows_nonexistent_dir(tmp_path: Path) -> None:
    target = tmp_path / "new-target"
    resolved = validate_target_path(str(target), scope_includes_grouping=True)
    assert resolved == target.resolve()


def test_validate_target_path_dedupe_only_returns_none() -> None:
    assert validate_target_path(None, scope_includes_grouping=False) is None


def test_validate_paths_rejects_same_and_nested(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValidationError):
        validate_paths(source, source)

    nested = source / "target"
    nested.mkdir()
    with pytest.raises(ValidationError):
        validate_paths(source, nested)


def test_validate_enum_helpers() -> None:
    assert validate_scope(ExecutionScope.GROUP_ONLY) == ExecutionScope.GROUP_ONLY
    assert validate_dedupe_mode(DedupeMode.QUARANTINE) == DedupeMode.QUARANTINE
    assert validate_organization_mode(OrganizationMode.COPY) == OrganizationMode.COPY

    with pytest.raises(ValidationError):
        validate_scope("group_only")  # type: ignore[arg-type]
