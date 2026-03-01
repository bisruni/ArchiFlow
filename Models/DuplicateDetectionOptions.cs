using FileGrouper.Services;
using System;
using System.Threading;

namespace FileGrouper.Models;

public sealed class DuplicateDetectionOptions
{
    public Action<string>? Log { get; init; }
    public Action<OperationProgress>? Progress { get; init; }
    public CancellationToken CancellationToken { get; init; }
    public PauseController? PauseController { get; init; }
    public HashCacheService? HashCache { get; init; }
    public bool DetectSimilarImages { get; init; }
    public int SimilarImageDistanceThreshold { get; init; } = 8;
}
