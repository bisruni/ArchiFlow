using FileGrouper.Models;
using System;
using System.Collections.Generic;

namespace FileGrouper.Services;

public static class FileClassifier
{
    private static readonly HashSet<string> ImageExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".tiff", ".svg", ".raw"
    };

    private static readonly HashSet<string> VideoExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".3gp"
    };

    private static readonly HashSet<string> AudioExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"
    };

    private static readonly HashSet<string> TextExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".txt", ".md", ".rtf", ".doc", ".docx", ".pdf", ".csv", ".json", ".xml", ".log"
    };

    private static readonly HashSet<string> ApplicationExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".exe", ".msi", ".dmg", ".pkg", ".app", ".apk", ".bat", ".cmd", ".ps1", ".sh", ".jar", ".iso"
    };

    private static readonly HashSet<string> ArchiveExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"
    };

    public static FileCategory Classify(string? extension)
    {
        if (string.IsNullOrWhiteSpace(extension))
        {
            return FileCategory.Other;
        }

        return extension.ToLowerInvariant() switch
        {
            var ext when ImageExtensions.Contains(ext) => FileCategory.Image,
            var ext when VideoExtensions.Contains(ext) => FileCategory.Video,
            var ext when AudioExtensions.Contains(ext) => FileCategory.Audio,
            var ext when TextExtensions.Contains(ext) => FileCategory.Text,
            var ext when ApplicationExtensions.Contains(ext) => FileCategory.Application,
            var ext when ArchiveExtensions.Contains(ext) => FileCategory.Archive,
            _ => FileCategory.Other
        };
    }

    public static string ToFolderName(FileCategory category) => category switch
    {
        FileCategory.Image => "images",
        FileCategory.Video => "videos",
        FileCategory.Audio => "audio",
        FileCategory.Text => "text",
        FileCategory.Application => "applications",
        FileCategory.Archive => "archives",
        _ => "other"
    };
}
