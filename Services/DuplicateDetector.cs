using FileGrouper.Models;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;

namespace FileGrouper.Services;

public sealed class DuplicateDetector
{
    public IReadOnlyList<DuplicateGroup> FindDuplicateGroups(
        IReadOnlyList<FileRecord> files,
        Action<string>? log = null)
    {
        return FindDuplicateData(files, new DuplicateDetectionOptions
        {
            Log = log
        }).DuplicateGroups;
    }

    public DuplicateDetectionResult FindDuplicateData(
        IReadOnlyList<FileRecord> files,
        DuplicateDetectionOptions? options = null)
    {
        options ??= new DuplicateDetectionOptions();
        var groups = new List<DuplicateGroup>();
        var cancellationToken = options.CancellationToken;
        var pauseController = options.PauseController;
        var hashIndex = 0;

        var sizeCollisions = files
            .GroupBy(f => f.SizeBytes)
            .Where(g => g.Count() > 1);

        foreach (var sizeGroup in sizeCollisions)
        {
            var byHash = new Dictionary<string, List<FileRecord>>(StringComparer.OrdinalIgnoreCase);

            foreach (var file in sizeGroup)
            {
                cancellationToken.ThrowIfCancellationRequested();
                pauseController?.Wait(cancellationToken);

                string hash;
                try
                {
                    hash = options.HashCache is not null
                        ? options.HashCache.GetOrComputeSha256(
                            file.FullPath,
                            file.SizeBytes,
                            file.LastWriteUtc,
                            () => ComputeSha256(file.FullPath))
                        : ComputeSha256(file.FullPath);
                }
                catch (Exception ex)
                {
                    options.Log?.Invoke($"Could not hash '{file.FullPath}': {ex.Message}");
                    continue;
                }

                if (!byHash.TryGetValue(hash, out var hashFiles))
                {
                    hashFiles = [];
                    byHash[hash] = hashFiles;
                }

                hashFiles.Add(file);
                hashIndex++;
                if (hashIndex % 100 == 0)
                {
                    options.Progress?.Invoke(new OperationProgress(
                        OperationStage.Hashing,
                        hashIndex,
                        files.Count,
                        "Computing hashes"));
                }
            }

            foreach (var duplicate in byHash.Where(kv => kv.Value.Count > 1))
            {
                var orderedFiles = duplicate.Value
                    .OrderBy(f => f.LastWriteUtc)
                    .ThenBy(f => f.FullPath, StringComparer.OrdinalIgnoreCase)
                    .ToArray();

                groups.Add(new DuplicateGroup(duplicate.Key, sizeGroup.Key, orderedFiles));
            }
        }

        var duplicateGroups = groups
            .OrderByDescending(g => g.Files.Count)
            .ThenByDescending(g => g.SizeBytes)
            .ToArray();

        IReadOnlyList<SimilarImageGroup> similarImages = [];
        if (options.DetectSimilarImages)
        {
            var similarDetector = new SimilarImageDetector();
            similarImages = similarDetector.FindSimilarImages(
                files,
                options.SimilarImageDistanceThreshold,
                options.Log,
                options.Progress,
                cancellationToken,
                pauseController);
        }

        return new DuplicateDetectionResult(duplicateGroups, similarImages);
    }

    private static string ComputeSha256(string path)
    {
        using var stream = File.OpenRead(path);
        var hash = SHA256.HashData(stream);
        return Convert.ToHexString(hash);
    }
}
