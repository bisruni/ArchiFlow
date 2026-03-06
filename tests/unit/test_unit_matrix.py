from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from archiflow.classifier import (
    APPLICATION_EXTENSIONS,
    ARCHIVE_EXTENSIONS,
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
    classify,
    folder_name,
    get_season,
)
from archiflow.models import FileCategory, ScanFilterOptions
from archiflow.utils import format_size
from archiflow.validators import validate_similarity_max_distance

EXT_CASES = (
    [(ext, FileCategory.IMAGE) for ext in sorted(IMAGE_EXTENSIONS)]
    + [(ext, FileCategory.VIDEO) for ext in sorted(VIDEO_EXTENSIONS)]
    + [(ext, FileCategory.AUDIO) for ext in sorted(AUDIO_EXTENSIONS)]
    + [(ext, FileCategory.TEXT) for ext in sorted(TEXT_EXTENSIONS)]
    + [(ext, FileCategory.APPLICATION) for ext in sorted(APPLICATION_EXTENSIONS)]
    + [(ext, FileCategory.ARCHIVE) for ext in sorted(ARCHIVE_EXTENSIONS)]
    + [(".unknown", FileCategory.OTHER)]
)


@pytest.mark.parametrize(("ext", "expected"), EXT_CASES)
def test_classify_extension_matrix(ext: str, expected: FileCategory) -> None:
    assert classify(Path(f"file{ext}")) is expected


@pytest.mark.parametrize(
    ("category", "expected_folder"),
    [
        (FileCategory.IMAGE, "Images"),
        (FileCategory.VIDEO, "Videos"),
        (FileCategory.AUDIO, "Audio"),
        (FileCategory.TEXT, "Documents"),
        (FileCategory.APPLICATION, "Other"),
        (FileCategory.ARCHIVE, "Other"),
        (FileCategory.OTHER, "Other"),
    ],
)
def test_folder_name_matrix(category: FileCategory, expected_folder: str) -> None:
    assert folder_name(category) == expected_folder


@pytest.mark.parametrize(("month", "season"), [(m, get_season(m)) for m in range(1, 13)])
def test_get_season_matrix(month: int, season: str) -> None:
    assert get_season(month) == season


@pytest.mark.parametrize("value", list(range(0, 65)))
def test_validate_similarity_max_distance_valid_matrix(value: int) -> None:
    assert validate_similarity_max_distance(value) == value


@pytest.mark.parametrize("value", [-10, -1, 65, 120, "abc", object()])
def test_validate_similarity_max_distance_invalid_matrix(value: object) -> None:
    with pytest.raises(Exception):
        validate_similarity_max_distance(value)


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [
        (0, "0 B"),
        (1, "1 B"),
        (1023, "1023 B"),
        (1024, "1.00 KB"),
        (1536, "1.50 KB"),
        (1024 * 1024, "1.00 MB"),
        (5 * 1024 * 1024, "5.00 MB"),
        (1024 * 1024 * 1024, "1.00 GB"),
        (3 * 1024 * 1024 * 1024, "3.00 GB"),
    ],
)
def test_format_size_matrix(num_bytes: int, expected: str) -> None:
    assert format_size(num_bytes) == expected


@pytest.mark.parametrize(
    ("path_name", "include", "exclude", "expected"),
    [
        ("a.jpg", [".jpg"], [], True),
        ("a.jpg", [".png"], [], False),
        ("a.tmp", [], [".tmp"], False),
        ("a.txt", [], [".tmp"], True),
        ("a.md", [".md", ".txt"], [".tmp"], True),
        ("a.bin", [".md", ".txt"], [".tmp"], False),
    ],
)
def test_scan_filter_extension_matrix(
    tmp_path: Path, path_name: str, include: list[str], exclude: list[str], expected: bool
) -> None:
    path = tmp_path / path_name
    path.write_text("x", encoding="utf-8")
    options = ScanFilterOptions(include_extensions=include, exclude_extensions=exclude)
    assert options.is_match(path) is expected


@pytest.mark.parametrize("size_bytes", [1, 128, 1024, 4096, 1024 * 1024, 2 * 1024 * 1024, 8 * 1024 * 1024])
def test_scan_filter_size_matrix(tmp_path: Path, size_bytes: int) -> None:
    path = tmp_path / f"{size_bytes}.bin"
    path.write_bytes(b"x" * size_bytes)
    options = ScanFilterOptions(min_size_bytes=1024, max_size_bytes=2 * 1024 * 1024)
    expected = 1024 <= size_bytes <= 2 * 1024 * 1024
    assert options.is_match(path) is expected


@pytest.mark.parametrize("days_offset", [-10, -1, 0, 1, 10])
def test_scan_filter_date_matrix(tmp_path: Path, days_offset: int) -> None:
    path = tmp_path / f"{days_offset}.txt"
    path.write_text("x", encoding="utf-8")

    ts = datetime.now(tz=timezone.utc) + timedelta(days=days_offset)
    dt = ts.timestamp()
    stat = path.stat()
    os.utime(path, (stat.st_atime, dt))

    from_utc = datetime.now(tz=timezone.utc) - timedelta(days=2)
    to_utc = datetime.now(tz=timezone.utc) + timedelta(days=2)
    options = ScanFilterOptions(from_utc=from_utc, to_utc=to_utc)
    expected = from_utc <= datetime.fromtimestamp(dt, tz=timezone.utc) <= to_utc
    assert options.is_match(path) is expected
