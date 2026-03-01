namespace FileGrouper.ViewModels;

public sealed class DuplicatePreviewItem
{
    public required string HashPrefix { get; init; }
    public required string KeepPath { get; init; }
    public required int RemoveCount { get; init; }
    public required string FileSize { get; init; }
}
