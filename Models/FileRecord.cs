using System;

namespace FileGrouper.Models;

public sealed record FileRecord(
    string FullPath,
    string Extension,
    long SizeBytes,
    DateTime LastWriteUtc,
    FileCategory Category
);
