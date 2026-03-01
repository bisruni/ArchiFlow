using System;
using System.Collections.Generic;

namespace FileGrouper.Models;

public sealed class OperationReportData
{
    public DateTime GeneratedAtUtc { get; init; } = DateTime.UtcNow;
    public string SourcePath { get; init; } = string.Empty;
    public string TargetPath { get; init; } = string.Empty;
    public OperationSummary Summary { get; init; } = new();
    public IReadOnlyList<DuplicateGroup> DuplicateGroups { get; init; } = [];
    public IReadOnlyList<SimilarImageGroup> SimilarImageGroups { get; init; } = [];
    public string? TransactionFilePath { get; init; }
}
