using FileGrouper.Models;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;

namespace FileGrouper.Services;

public sealed class FileScanner
{
    public IReadOnlyList<FileRecord> Scan(string sourcePath, Action<string>? log = null)
    {
        return Scan(sourcePath, new ScanExecutionOptions
        {
            Log = log
        });
    }

    public IReadOnlyList<FileRecord> Scan(string sourcePath, ScanExecutionOptions? options)
    {
        if (!Directory.Exists(sourcePath))
        {
            throw new DirectoryNotFoundException($"Source folder not found: {sourcePath}");
        }

        options ??= new ScanExecutionOptions();
        var cancellationToken = options.CancellationToken;
        var records = new List<FileRecord>();
        var scanned = 0;

        foreach (var fullPath in EnumerateFilesSafely(sourcePath, options.Log))
        {
            cancellationToken.ThrowIfCancellationRequested();
            options.PauseController?.Wait(cancellationToken);

            try
            {
                var info = new FileInfo(fullPath);
                if (!info.Exists)
                {
                    continue;
                }

                if (options.Filter is not null && !options.Filter.IsMatch(info))
                {
                    continue;
                }

                var extension = info.Extension;
                var size = info.Length;
                var lastWriteUtc = info.LastWriteTimeUtc;

                records.Add(
                    new FileRecord(
                        info.FullName,
                        extension,
                        size,
                        lastWriteUtc,
                        FileClassifier.Classify(extension)));
            }
            catch (Exception ex)
            {
                options.Log?.Invoke($"Could not inspect file '{fullPath}': {ex.Message}");
            }

            scanned++;
            if (scanned % 100 == 0)
            {
                options.Progress?.Invoke(new OperationProgress(
                    OperationStage.Scanning,
                    scanned,
                    0,
                    "Scanning files"));
            }
        }

        return records
            .OrderBy(r => r.Category)
            .ThenBy(r => r.LastWriteUtc)
            .ThenBy(r => r.FullPath, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static IEnumerable<string> EnumerateFilesSafely(string rootPath, Action<string>? log)
    {
        var pending = new Stack<string>();
        pending.Push(rootPath);

        while (pending.Count > 0)
        {
            var current = pending.Pop();

            IEnumerable<string> files = Array.Empty<string>();
            IEnumerable<string> dirs = Array.Empty<string>();

            try
            {
                files = Directory.EnumerateFiles(current);
            }
            catch (Exception ex)
            {
                log?.Invoke($"Could not read files in '{current}': {ex.Message}");
            }

            foreach (var file in files)
            {
                yield return file;
            }

            try
            {
                dirs = Directory.EnumerateDirectories(current);
            }
            catch (Exception ex)
            {
                log?.Invoke($"Could not read folders in '{current}': {ex.Message}");
            }

            foreach (var dir in dirs)
            {
                if (IsSymlink(dir))
                {
                    continue;
                }

                if (string.Equals(Path.GetFileName(dir), "Duplicates_Quarantine", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                pending.Push(dir);
            }
        }
    }

    private static bool IsSymlink(string dirPath)
    {
        try
        {
            var attributes = File.GetAttributes(dirPath);
            return (attributes & FileAttributes.ReparsePoint) == FileAttributes.ReparsePoint;
        }
        catch
        {
            return false;
        }
    }
}
