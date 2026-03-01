using System.Collections.Generic;

namespace FileGrouper.Models;

public sealed record SimilarImageGroup(
    string AnchorPath,
    IReadOnlyList<string> SimilarPaths,
    int MaxDistance
);
