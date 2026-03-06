from __future__ import annotations

from datetime import datetime, timezone

from archiflow.models import DedupeMode, ExecutionScope, OperationProfile, OrganizationMode, ScanFilterOptions


def test_operation_profile_roundtrip() -> None:
    profile = OperationProfile(
        name="test-profile",
        execution_scope=ExecutionScope.DEDUPE_ONLY,
        organization_mode=OrganizationMode.MOVE,
        dedupe_mode=DedupeMode.QUARANTINE,
        is_dry_run=False,
        detect_similar_images=True,
        filter_options=ScanFilterOptions(
            include_extensions=[".jpg"],
            exclude_extensions=[".tmp"],
            min_size_bytes=1024,
            max_size_bytes=2048,
            from_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            to_utc=datetime(2025, 12, 31, tzinfo=timezone.utc),
        ),
    )

    payload = profile.to_dict()
    restored = OperationProfile.from_dict(payload)

    assert restored.name == profile.name
    assert restored.execution_scope == profile.execution_scope
    assert restored.organization_mode == profile.organization_mode
    assert restored.dedupe_mode == profile.dedupe_mode
    assert restored.is_dry_run == profile.is_dry_run
    assert restored.detect_similar_images == profile.detect_similar_images
    assert restored.filter_options.include_extensions == [".jpg"]
    assert restored.filter_options.exclude_extensions == [".tmp"]
    assert restored.filter_options.min_size_bytes == 1024
    assert restored.filter_options.max_size_bytes == 2048


def test_execution_scope_flags() -> None:
    assert ExecutionScope.GROUP_AND_DEDUPE.includes_grouping is True
    assert ExecutionScope.GROUP_AND_DEDUPE.includes_dedupe is True
    assert ExecutionScope.GROUP_ONLY.includes_grouping is True
    assert ExecutionScope.GROUP_ONLY.includes_dedupe is False
    assert ExecutionScope.DEDUPE_ONLY.includes_grouping is False
    assert ExecutionScope.DEDUPE_ONLY.includes_dedupe is True
