using FileGrouper.Services;

namespace FileGrouper.Models;

public sealed class OperationProfile
{
    public string Name { get; init; } = string.Empty;
    public string ExecutionScope { get; init; } = "GroupAndDedupe";
    public OrganizationMode OrganizationMode { get; init; } = OrganizationMode.Copy;
    public DedupeMode DedupeMode { get; init; } = DedupeMode.Quarantine;
    public bool IsDryRun { get; init; } = true;
    public bool DetectSimilarImages { get; init; }
    public ScanFilterOptions Filter { get; init; } = new();
}
