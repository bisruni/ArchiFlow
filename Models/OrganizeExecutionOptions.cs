using FileGrouper.Services;
using System;
using System.Threading;

namespace FileGrouper.Models;

public sealed class OrganizeExecutionOptions
{
    public Action<OperationProgress>? Progress { get; init; }
    public Action<string>? Log { get; init; }
    public CancellationToken CancellationToken { get; init; }
    public PauseController? PauseController { get; init; }
    public OperationTransaction? Transaction { get; init; }
}
