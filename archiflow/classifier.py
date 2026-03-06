"""File type classification helpers used by scanner and organizer layers."""

from __future__ import annotations

from pathlib import Path

from .models import FileCategory

IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".tiff", ".svg", ".raw"}
)
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".3gp"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"})
TEXT_EXTENSIONS = frozenset({".txt", ".md", ".rtf", ".doc", ".docx", ".pdf", ".csv", ".json", ".xml", ".log"})
APPLICATION_EXTENSIONS = frozenset(
    {".exe", ".msi", ".dmg", ".pkg", ".app", ".apk", ".bat", ".cmd", ".ps1", ".sh", ".jar", ".iso"}
)
ARCHIVE_EXTENSIONS = frozenset({".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"})


def classify(path: Path) -> FileCategory:
    """Return the logical file category based on extension."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return FileCategory.IMAGE
    if ext in VIDEO_EXTENSIONS:
        return FileCategory.VIDEO
    if ext in AUDIO_EXTENSIONS:
        return FileCategory.AUDIO
    if ext in TEXT_EXTENSIONS:
        return FileCategory.TEXT
    if ext in APPLICATION_EXTENSIONS:
        return FileCategory.APPLICATION
    if ext in ARCHIVE_EXTENSIONS:
        return FileCategory.ARCHIVE
    return FileCategory.OTHER


def folder_name(category: FileCategory) -> str:
    """Map a category to its destination root folder name."""
    return {
        FileCategory.IMAGE: "Images",
        FileCategory.VIDEO: "Videos",
        FileCategory.AUDIO: "Audio",
        FileCategory.TEXT: "Documents",
        FileCategory.APPLICATION: "Other",
        FileCategory.ARCHIVE: "Other",
        FileCategory.OTHER: "Other",
    }[category]


def get_season(month: int) -> str:
    """Map month number (1-12) to an English season name."""
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    if month in (9, 10, 11):
        return "Fall"
    raise ValueError(f"Invalid month: {month}")
