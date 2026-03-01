using FileGrouper.Models;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace FileGrouper.Services;

public enum OrganizationMode
{
    Copy,
    Move
}

public enum DedupeMode
{
    Off,
    Quarantine,
    Delete
}

public sealed class FileOrganizer
{
    public void OrganizeByCategoryAndDate(
        IReadOnlyList<FileRecord> files,
        string targetRoot,
        OrganizationMode mode,
        bool dryRun,
        OperationSummary summary)
    {
        OrganizeByCategoryAndDate(
            files,
            targetRoot,
            mode,
            dryRun,
            summary,
            options: null);
    }

    public void OrganizeByCategoryAndDate(
        IReadOnlyList<FileRecord> files,
        string targetRoot,
        OrganizationMode mode,
        bool dryRun,
        OperationSummary summary,
        OrganizeExecutionOptions? options)
    {
        options ??= new OrganizeExecutionOptions();
        var cancellationToken = options.CancellationToken;

        if (!dryRun)
        {
            Directory.CreateDirectory(targetRoot);
        }

        var processed = 0;
        foreach (var file in files)
        {
            cancellationToken.ThrowIfCancellationRequested();
            options.PauseController?.Wait(cancellationToken);

            if (!File.Exists(file.FullPath))
            {
                continue;
            }

            var localWriteTime = file.LastWriteUtc.ToLocalTime();
            var year = localWriteTime.Year.ToString(CultureInfo.InvariantCulture);
            var month = localWriteTime.Month.ToString("00", CultureInfo.InvariantCulture);
            var categoryFolder = FileClassifier.ToFolderName(file.Category);
            var destinationFolder = Path.Combine(targetRoot, categoryFolder, year, month);
            var destinationPath = BuildUniquePath(destinationFolder, Path.GetFileName(file.FullPath));

            if (dryRun)
            {
                if (mode == OrganizationMode.Copy)
                {
                    summary.FilesCopied++;
                }
                else
                {
                    summary.FilesMoved++;
                }

                continue;
            }

            try
            {
                Directory.CreateDirectory(destinationFolder);

                if (mode == OrganizationMode.Copy)
                {
                    File.Copy(file.FullPath, destinationPath, overwrite: false);
                    summary.FilesCopied++;
                    options.Transaction?.Entries.Add(
                        new TransactionEntry(
                            TransactionAction.Copied,
                            file.FullPath,
                            destinationPath,
                            DateTime.UtcNow));
                }
                else
                {
                    File.Move(file.FullPath, destinationPath);
                    summary.FilesMoved++;
                    options.Transaction?.Entries.Add(
                        new TransactionEntry(
                            TransactionAction.Moved,
                            file.FullPath,
                            destinationPath,
                            DateTime.UtcNow));
                }
            }
            catch (Exception ex)
            {
                summary.Errors.Add($"Could not process '{file.FullPath}': {ex.Message}");
                options.Log?.Invoke($"Could not process '{file.FullPath}': {ex.Message}");
            }

            processed++;
            if (processed % 50 == 0)
            {
                options.Progress?.Invoke(new OperationProgress(
                    OperationStage.Organizing,
                    processed,
                    files.Count,
                    "Organizing files"));
            }
        }
    }

    public IReadOnlyList<FileRecord> ProcessDuplicates(
        IReadOnlyList<DuplicateGroup> duplicateGroups,
        DedupeMode dedupeMode,
        string sourceRoot,
        bool dryRun,
        OperationSummary summary)
    {
        return ProcessDuplicates(
            duplicateGroups,
            dedupeMode,
            sourceRoot,
            dryRun,
            summary,
            options: null);
    }

    public IReadOnlyList<FileRecord> ProcessDuplicates(
        IReadOnlyList<DuplicateGroup> duplicateGroups,
        DedupeMode dedupeMode,
        string sourceRoot,
        bool dryRun,
        OperationSummary summary,
        OrganizeExecutionOptions? options)
    {
        options ??= new OrganizeExecutionOptions();
        var cancellationToken = options.CancellationToken;

        if (dedupeMode == DedupeMode.Off)
        {
            return [];
        }

        var toRemove = duplicateGroups
            .SelectMany(group => group.Files.Skip(1))
            .DistinctBy(file => file.FullPath, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        if (toRemove.Length == 0)
        {
            return [];
        }

        var quarantineRoot = Path.Combine(
            sourceRoot,
            "Duplicates_Quarantine",
            DateTime.Now.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture));

        var processed = 0;
        foreach (var duplicate in toRemove)
        {
            cancellationToken.ThrowIfCancellationRequested();
            options.PauseController?.Wait(cancellationToken);

            if (!File.Exists(duplicate.FullPath))
            {
                continue;
            }

            try
            {
                if (dedupeMode == DedupeMode.Delete)
                {
                    if (!dryRun)
                    {
                        File.Delete(duplicate.FullPath);
                    }

                    summary.DuplicatesDeleted++;
                    options.Transaction?.Entries.Add(
                        new TransactionEntry(
                            TransactionAction.DeletedDuplicate,
                            duplicate.FullPath,
                            string.Empty,
                            DateTime.UtcNow));
                    continue;
                }

                var relative = Path.GetRelativePath(sourceRoot, duplicate.FullPath);
                var destination = BuildQuarantinePath(quarantineRoot, relative);

                if (dryRun)
                {
                    summary.DuplicatesQuarantined++;
                    continue;
                }

                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                File.Move(duplicate.FullPath, destination);
                summary.DuplicatesQuarantined++;
                options.Transaction?.Entries.Add(
                    new TransactionEntry(
                        TransactionAction.QuarantinedDuplicate,
                        duplicate.FullPath,
                        destination,
                        DateTime.UtcNow));
            }
            catch (Exception ex)
            {
                summary.Errors.Add($"Could not process duplicate '{duplicate.FullPath}': {ex.Message}");
                options.Log?.Invoke($"Could not process duplicate '{duplicate.FullPath}': {ex.Message}");
            }

            processed++;
            if (processed % 50 == 0)
            {
                options.Progress?.Invoke(new OperationProgress(
                    OperationStage.Organizing,
                    processed,
                    toRemove.Length,
                    "Processing duplicates"));
            }
        }

        return toRemove;
    }

    private static string BuildQuarantinePath(string quarantineRoot, string relativePath)
    {
        var safeRelativePath = relativePath;
        if (Path.IsPathRooted(safeRelativePath) || safeRelativePath.StartsWith("..", StringComparison.Ordinal))
        {
            safeRelativePath = Path.GetFileName(relativePath);
        }

        var destination = Path.Combine(quarantineRoot, safeRelativePath);
        var folder = Path.GetDirectoryName(destination) ?? quarantineRoot;
        var filename = Path.GetFileName(destination);
        return BuildUniquePath(folder, filename);
    }

    private static string BuildUniquePath(string directory, string fileName)
    {
        var candidate = Path.Combine(directory, fileName);
        if (!File.Exists(candidate))
        {
            return candidate;
        }

        var baseName = Path.GetFileNameWithoutExtension(fileName);
        var extension = Path.GetExtension(fileName);

        for (var i = 1; ; i++)
        {
            var uniqueName = $"{baseName}_{i}{extension}";
            candidate = Path.Combine(directory, uniqueName);
            if (!File.Exists(candidate))
            {
                return candidate;
            }
        }
    }
}
