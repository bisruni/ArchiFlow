namespace FileGrouper.Models;

public enum OperationStage
{
    Idle,
    Scanning,
    Hashing,
    Similarity,
    Organizing,
    Reporting,
    Undo,
    Completed
}

public sealed record OperationProgress(
    OperationStage Stage,
    int ProcessedFiles,
    int TotalFiles,
    string Message
);
