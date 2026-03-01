using System.Collections.Generic;

namespace FileGrouper.Models;

public sealed record DuplicateGroup(
    string Hash,
    long SizeBytes,
    IReadOnlyList<FileRecord> Files
);
