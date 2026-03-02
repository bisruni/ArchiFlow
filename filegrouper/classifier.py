from __future__ import annotations

from pathlib import Path

from .models import FileCategory


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".tiff", ".svg", ".raw"
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".3gp"
}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"
}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".rtf", ".doc", ".docx", ".pdf", ".csv", ".json", ".xml", ".log"
}
APPLICATION_EXTENSIONS = {
    ".exe", ".msi", ".dmg", ".pkg", ".app", ".apk", ".bat", ".cmd", ".ps1", ".sh", ".jar", ".iso"
}
ARCHIVE_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"
}


def classify(path: Path) -> FileCategory:
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
    return {
        FileCategory.IMAGE: "images",
        FileCategory.VIDEO: "videos",
        FileCategory.AUDIO: "audio",
        FileCategory.TEXT: "text",
        FileCategory.APPLICATION: "applications",
        FileCategory.ARCHIVE: "archives",
        FileCategory.OTHER: "other",
    }[category]
