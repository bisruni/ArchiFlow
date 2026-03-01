using FileGrouper.Services;
using System;
using System.Threading;

namespace FileGrouper.Models;

public sealed class ScanExecutionOptions
{
    public ScanFilterOptions? Filter { get; init; }
    public Action<string>? Log { get; init; }
    public Action<OperationProgress>? Progress { get; init; }
    public CancellationToken CancellationToken { get; init; }
    public PauseController? PauseController { get; init; }
}
