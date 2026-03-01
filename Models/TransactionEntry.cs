using System;

namespace FileGrouper.Models;

public enum TransactionAction
{
    Copied,
    Moved,
    QuarantinedDuplicate,
    DeletedDuplicate
}

public sealed record TransactionEntry(
    TransactionAction Action,
    string SourcePath,
    string DestinationPath,
    DateTime TimestampUtc
);
