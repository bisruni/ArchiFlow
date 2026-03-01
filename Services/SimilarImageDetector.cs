using FileGrouper.Models;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;

namespace FileGrouper.Services;

public sealed class SimilarImageDetector
{
    private static readonly HashSet<string> SupportedImageExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".heic"
    };

    public IReadOnlyList<SimilarImageGroup> FindSimilarImages(
        IReadOnlyList<FileRecord> files,
        int maxDistance,
        Action<string>? log,
        Action<OperationProgress>? progress,
        CancellationToken cancellationToken,
        PauseController? pauseController)
    {
        var images = files
            .Where(f => SupportedImageExtensions.Contains(f.Extension))
            .ToArray();

        if (images.Length < 2)
        {
            return [];
        }

        var fingerprints = new List<(FileRecord File, ulong Fingerprint)>(images.Length);
        var processed = 0;

        foreach (var image in images)
        {
            cancellationToken.ThrowIfCancellationRequested();
            pauseController?.Wait(cancellationToken);

            try
            {
                fingerprints.Add((image, ComputeByteFingerprint(image.FullPath)));
            }
            catch (Exception ex)
            {
                log?.Invoke($"Could not compute similarity fingerprint for '{image.FullPath}': {ex.Message}");
            }

            processed++;
            progress?.Invoke(new OperationProgress(
                OperationStage.Similarity,
                processed,
                images.Length,
                "Computing similarity fingerprints"));
        }

        if (fingerprints.Count < 2)
        {
            return [];
        }

        var uf = new UnionFind(fingerprints.Count);

        for (var i = 0; i < fingerprints.Count; i++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            pauseController?.Wait(cancellationToken);

            for (var j = i + 1; j < fingerprints.Count; j++)
            {
                // Extra guard by relative size to avoid unrelated files.
                var a = fingerprints[i].File.SizeBytes;
                var b = fingerprints[j].File.SizeBytes;
                var ratio = a == 0 || b == 0 ? 0 : Math.Min(a, b) / (double)Math.Max(a, b);
                if (ratio < 0.70)
                {
                    continue;
                }

                var distance = HammingDistance(fingerprints[i].Fingerprint, fingerprints[j].Fingerprint);
                if (distance <= maxDistance)
                {
                    uf.Union(i, j);
                }
            }
        }

        var groups = new Dictionary<int, List<FileRecord>>();
        for (var i = 0; i < fingerprints.Count; i++)
        {
            var root = uf.Find(i);
            if (!groups.TryGetValue(root, out var list))
            {
                list = [];
                groups[root] = list;
            }

            list.Add(fingerprints[i].File);
        }

        return groups.Values
            .Where(g => g.Count > 1)
            .Select(g =>
            {
                var ordered = g.OrderBy(x => x.LastWriteUtc).ToArray();
                return new SimilarImageGroup(
                    ordered[0].FullPath,
                    ordered.Skip(1).Select(x => x.FullPath).ToArray(),
                    maxDistance);
            })
            .OrderByDescending(g => g.SimilarPaths.Count)
            .ToArray();
    }

    private static ulong ComputeByteFingerprint(string path)
    {
        using var stream = File.OpenRead(path);
        var length = stream.Length;
        if (length == 0)
        {
            return 0;
        }

        Span<byte> sample = stackalloc byte[64];
        var offsets = new long[]
        {
            0,
            Math.Max(0, length / 4 - 8),
            Math.Max(0, length / 2 - 8),
            Math.Max(0, (length * 3) / 4 - 8),
            Math.Max(0, length - 16)
        };

        var idx = 0;
        foreach (var offset in offsets)
        {
            stream.Seek(offset, SeekOrigin.Begin);
            var toRead = Math.Min(12, sample.Length - idx);
            var read = stream.Read(sample.Slice(idx, toRead));
            idx += read;
            if (idx >= sample.Length)
            {
                break;
            }
        }

        ulong fingerprint = 1469598103934665603UL; // FNV offset basis
        for (var i = 0; i < idx; i++)
        {
            fingerprint ^= sample[i];
            fingerprint *= 1099511628211UL;
        }

        return fingerprint;
    }

    private static int HammingDistance(ulong a, ulong b)
    {
        var x = a ^ b;
        var count = 0;
        while (x != 0)
        {
            x &= x - 1;
            count++;
        }

        return count;
    }

    private sealed class UnionFind(int size)
    {
        private readonly int[] _parent = Enumerable.Range(0, size).ToArray();
        private readonly int[] _rank = new int[size];

        public int Find(int x)
        {
            if (_parent[x] != x)
            {
                _parent[x] = Find(_parent[x]);
            }

            return _parent[x];
        }

        public void Union(int a, int b)
        {
            var rootA = Find(a);
            var rootB = Find(b);
            if (rootA == rootB)
            {
                return;
            }

            if (_rank[rootA] < _rank[rootB])
            {
                _parent[rootA] = rootB;
            }
            else if (_rank[rootA] > _rank[rootB])
            {
                _parent[rootB] = rootA;
            }
            else
            {
                _parent[rootB] = rootA;
                _rank[rootA]++;
            }
        }
    }
}
