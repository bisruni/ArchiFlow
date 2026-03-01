using System;
using System.Collections.Generic;

namespace FileGrouper.Models;

public sealed class OperationTransaction
{
    public string TransactionId { get; init; } = Guid.NewGuid().ToString("N");
    public DateTime CreatedAtUtc { get; init; } = DateTime.UtcNow;
    public string SourceRoot { get; init; } = string.Empty;
    public string TargetRoot { get; init; } = string.Empty;
    public List<TransactionEntry> Entries { get; } = [];
}
