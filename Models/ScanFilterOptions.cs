using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace FileGrouper.Models;

public sealed class ScanFilterOptions
{
    public List<string> IncludeExtensions { get; init; } = [];
    public List<string> ExcludeExtensions { get; init; } = [];
    public long? MinSizeBytes { get; init; }
    public long? MaxSizeBytes { get; init; }
    public DateTime? FromUtc { get; init; }
    public DateTime? ToUtc { get; init; }
    public bool ExcludeHidden { get; init; } = true;
    public bool ExcludeSystem { get; init; } = true;

    public bool IsMatch(FileInfo info)
    {
        var ext = NormalizeExtension(info.Extension);
        var include = IncludeExtensions.Select(NormalizeExtension).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var exclude = ExcludeExtensions.Select(NormalizeExtension).ToHashSet(StringComparer.OrdinalIgnoreCase);

        if (include.Count > 0 && !include.Contains(ext))
        {
            return false;
        }

        if (exclude.Contains(ext))
        {
            return false;
        }

        if (MinSizeBytes.HasValue && info.Length < MinSizeBytes.Value)
        {
            return false;
        }

        if (MaxSizeBytes.HasValue && info.Length > MaxSizeBytes.Value)
        {
            return false;
        }

        if (FromUtc.HasValue && info.LastWriteTimeUtc < FromUtc.Value)
        {
            return false;
        }

        if (ToUtc.HasValue && info.LastWriteTimeUtc > ToUtc.Value)
        {
            return false;
        }

        if (ExcludeHidden && IsHidden(info))
        {
            return false;
        }

        if (ExcludeSystem && IsSystem(info))
        {
            return false;
        }

        return true;
    }

    public static string NormalizeExtension(string extension)
    {
        if (string.IsNullOrWhiteSpace(extension))
        {
            return string.Empty;
        }

        return extension.StartsWith(".", StringComparison.Ordinal) ? extension.ToLowerInvariant() : $".{extension.ToLowerInvariant()}";
    }

    private static bool IsHidden(FileInfo info)
    {
        var isDotFile = info.Name.StartsWith(".", StringComparison.Ordinal);
        var attr = info.Attributes;
        return isDotFile || (attr & FileAttributes.Hidden) == FileAttributes.Hidden;
    }

    private static bool IsSystem(FileInfo info)
    {
        var attr = info.Attributes;
        return (attr & FileAttributes.System) == FileAttributes.System;
    }
}
