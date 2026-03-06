from __future__ import annotations

from pathlib import Path

import pytest

from archiflow.classifier import classify, folder_name, get_season
from archiflow.models import FileCategory


def test_classify_known_extensions() -> None:
    assert classify(Path("photo.jpg")) == FileCategory.IMAGE
    assert classify(Path("movie.mp4")) == FileCategory.VIDEO
    assert classify(Path("voice.mp3")) == FileCategory.AUDIO
    assert classify(Path("report.pdf")) == FileCategory.TEXT
    assert classify(Path("archive.zip")) == FileCategory.ARCHIVE


def test_classify_unknown_extension() -> None:
    assert classify(Path("file.unknown")) == FileCategory.OTHER


def test_folder_name_mapping() -> None:
    assert folder_name(FileCategory.IMAGE) == "Images"
    assert folder_name(FileCategory.TEXT) == "Documents"
    assert folder_name(FileCategory.OTHER) == "Other"


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (1, "Winter"),
        (4, "Spring"),
        (7, "Summer"),
        (10, "Fall"),
    ],
)
def test_get_season_valid_months(month: int, expected: str) -> None:
    assert get_season(month) == expected


def test_get_season_invalid_month() -> None:
    with pytest.raises(ValueError):
        get_season(13)
