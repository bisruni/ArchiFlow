using System.Collections.Generic;

namespace FileGrouper.Models;

public sealed record DuplicateDetectionResult(
    IReadOnlyList<DuplicateGroup> DuplicateGroups,
    IReadOnlyList<SimilarImageGroup> SimilarImageGroups
);
