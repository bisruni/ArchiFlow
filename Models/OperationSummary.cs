using System.Collections.Generic;

namespace FileGrouper.Models;

public sealed class OperationSummary
{
    public int TotalFilesScanned { get; init; }
    public long TotalBytesScanned { get; init; }
    public int DuplicateGroupCount { get; init; }
    public int DuplicateFilesFound { get; init; }
    public long DuplicateBytesReclaimable { get; init; }
    public int FilesCopied { get; set; }
    public int FilesMoved { get; set; }
    public int DuplicatesQuarantined { get; set; }
    public int DuplicatesDeleted { get; set; }
    public List<string> Errors { get; } = [];
}
