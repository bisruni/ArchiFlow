using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

namespace FileGrouper.Services;

public sealed class HashCacheService
{
    private readonly string _cachePath;
    private readonly object _sync = new();
    private Dictionary<string, CacheEntry>? _cache;

    public HashCacheService(string cachePath)
    {
        _cachePath = cachePath;
    }

    public string GetOrComputeSha256(string path, long sizeBytes, DateTime lastWriteUtc, Func<string> computeHash)
    {
        var key = NormalizePath(path);
        var ticks = lastWriteUtc.Ticks;

        lock (_sync)
        {
            LoadIfNeeded();
            if (_cache!.TryGetValue(key, out var entry)
                && entry.SizeBytes == sizeBytes
                && entry.LastWriteTicks == ticks
                && !string.IsNullOrWhiteSpace(entry.Sha256))
            {
                return entry.Sha256;
            }
        }

        var hash = computeHash();

        lock (_sync)
        {
            LoadIfNeeded();
            _cache![key] = new CacheEntry
            {
                SizeBytes = sizeBytes,
                LastWriteTicks = ticks,
                Sha256 = hash
            };
            Save();
        }

        return hash;
    }

    private void LoadIfNeeded()
    {
        if (_cache is not null)
        {
            return;
        }

        if (!File.Exists(_cachePath))
        {
            _cache = new Dictionary<string, CacheEntry>(StringComparer.OrdinalIgnoreCase);
            return;
        }

        try
        {
            var json = File.ReadAllText(_cachePath);
            _cache = JsonSerializer.Deserialize<Dictionary<string, CacheEntry>>(json)
                     ?? new Dictionary<string, CacheEntry>(StringComparer.OrdinalIgnoreCase);
        }
        catch
        {
            _cache = new Dictionary<string, CacheEntry>(StringComparer.OrdinalIgnoreCase);
        }
    }

    private void Save()
    {
        var directory = Path.GetDirectoryName(_cachePath);
        if (!string.IsNullOrWhiteSpace(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var json = JsonSerializer.Serialize(_cache, new JsonSerializerOptions { WriteIndented = false });
        File.WriteAllText(_cachePath, json);
    }

    private static string NormalizePath(string path)
    {
        return Path.GetFullPath(path)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            .ToLowerInvariant();
    }

    private sealed class CacheEntry
    {
        public long SizeBytes { get; init; }
        public long LastWriteTicks { get; init; }
        public string Sha256 { get; init; } = string.Empty;
    }
}
