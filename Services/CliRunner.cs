using FileGrouper.Models;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace FileGrouper.Services;

public static class CliRunner
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true
    };

    public static bool IsCliCommand(string[] args)
    {
        if (args.Length == 0)
        {
            return false;
        }

        return args[0].Equals("scan", StringComparison.OrdinalIgnoreCase)
            || args[0].Equals("preview", StringComparison.OrdinalIgnoreCase)
            || args[0].Equals("apply", StringComparison.OrdinalIgnoreCase)
            || args[0].Equals("help", StringComparison.OrdinalIgnoreCase)
            || args[0].Equals("--help", StringComparison.OrdinalIgnoreCase)
            || args[0].Equals("-h", StringComparison.OrdinalIgnoreCase);
    }

    public static int Run(string[] args)
    {
        if (args.Length == 0 || args[0] is "--help" or "-h" or "help")
        {
            PrintUsage();
            return 0;
        }

        var command = args[0].ToLowerInvariant();
        var parsed = ParseArgs(args.Skip(1).ToArray());

        return command switch
        {
            "scan" => RunScan(parsed),
            "preview" => RunPreview(parsed),
            "apply" => RunApply(parsed),
            _ => Fail($"Unknown command: {args[0]}")
        };
    }

    private static int RunScan(ParsedArgs args)
    {
        var source = RequireDirectoryArg(args, "--source");
        if (source is null)
        {
            return 1;
        }

        var scanner = new FileScanner();
        var files = scanner.Scan(source, Console.WriteLine);
        var report = BuildReport(source, files, duplicateGroups: []);

        PrintReportSummary(report, "Scan result");
        WriteReportIfRequested(args, report);
        return 0;
    }

    private static int RunPreview(ParsedArgs args)
    {
        var source = RequireDirectoryArg(args, "--source");
        if (source is null)
        {
            return 1;
        }

        var scanner = new FileScanner();
        var detector = new DuplicateDetector();

        var files = scanner.Scan(source, Console.WriteLine);
        var duplicates = detector.FindDuplicateGroups(files, Console.WriteLine);
        var report = BuildReport(source, files, duplicates);

        PrintReportSummary(report, "Preview result");
        PrintDuplicateHighlights(duplicates);
        WriteReportIfRequested(args, report);
        return 0;
    }

    private static int RunApply(ParsedArgs args)
    {
        var source = RequireDirectoryArg(args, "--source");
        if (source is null)
        {
            return 1;
        }

        var target = RequirePathArg(args, "--target");
        if (target is null)
        {
            return 1;
        }

        var mode = ParseOrganizationMode(args.GetValue("--mode"));
        if (mode is null)
        {
            return Fail("Invalid --mode value. Use: copy or move.");
        }

        var dedupeMode = ParseDedupeMode(args.GetValue("--dedupe"));
        if (dedupeMode is null)
        {
            return Fail("Invalid --dedupe value. Use: off, quarantine, or delete.");
        }

        if (PathsEqual(source, target))
        {
            return Fail("Source and target cannot be the same path.");
        }

        if (IsSubPathOf(target, source))
        {
            return Fail("Target cannot be inside source. Choose a folder outside --source.");
        }

        var dryRun = args.HasFlag("--dry-run");
        var scanner = new FileScanner();
        var detector = new DuplicateDetector();
        var organizer = new FileOrganizer();

        var files = scanner.Scan(source, Console.WriteLine);
        var duplicates = detector.FindDuplicateGroups(files, Console.WriteLine);
        var summary = BuildOperationSummary(files, duplicates);
        var filesToSkip = organizer.ProcessDuplicates(duplicates, dedupeMode.Value, source, dryRun, summary);
        var skipSet = filesToSkip.Select(f => f.FullPath).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var filteredFiles = files.Where(f => !skipSet.Contains(f.FullPath)).ToArray();

        organizer.OrganizeByCategoryAndDate(filteredFiles, target, mode.Value, dryRun, summary);

        PrintOperationSummary(summary, dryRun, source, target, mode.Value, dedupeMode.Value);
        WriteReportIfRequested(args, summary);
        return 0;
    }

    private static bool PathsEqual(string a, string b)
    {
        var normalizedA = Path.GetFullPath(a)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var normalizedB = Path.GetFullPath(b)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return string.Equals(normalizedA, normalizedB, StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsSubPathOf(string candidatePath, string rootPath)
    {
        var candidate = Path.GetFullPath(candidatePath)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        var root = Path.GetFullPath(rootPath)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;
        return candidate.StartsWith(root, StringComparison.OrdinalIgnoreCase);
    }

    private static OperationSummary BuildOperationSummary(
        IReadOnlyList<FileRecord> files,
        IReadOnlyList<DuplicateGroup> duplicateGroups)
    {
        var duplicateFiles = duplicateGroups.Sum(g => g.Files.Count - 1);
        var duplicateBytes = duplicateGroups.Sum(g => g.SizeBytes * (g.Files.Count - 1));

        return new OperationSummary
        {
            TotalFilesScanned = files.Count,
            TotalBytesScanned = files.Sum(f => f.SizeBytes),
            DuplicateGroupCount = duplicateGroups.Count,
            DuplicateFilesFound = duplicateFiles,
            DuplicateBytesReclaimable = duplicateBytes
        };
    }

    private static object BuildReport(
        string sourcePath,
        IReadOnlyList<FileRecord> files,
        IReadOnlyList<DuplicateGroup> duplicateGroups)
    {
        var grouped = files
            .GroupBy(f => new
            {
                f.Category,
                YearMonth = f.LastWriteUtc.ToLocalTime().ToString("yyyy-MM", CultureInfo.InvariantCulture)
            })
            .Select(g => new
            {
                category = g.Key.Category.ToString(),
                yearMonth = g.Key.YearMonth,
                count = g.Count(),
                totalBytes = g.Sum(x => x.SizeBytes)
            })
            .OrderBy(g => g.category)
            .ThenBy(g => g.yearMonth)
            .ToArray();

        var byCategory = files
            .GroupBy(f => f.Category)
            .Select(g => new
            {
                category = g.Key.ToString(),
                count = g.Count(),
                totalBytes = g.Sum(x => x.SizeBytes)
            })
            .OrderBy(g => g.category)
            .ToArray();

        var duplicateFiles = duplicateGroups.Sum(g => g.Files.Count - 1);
        var reclaimableBytes = duplicateGroups.Sum(g => g.SizeBytes * (g.Files.Count - 1));

        return new
        {
            generatedAtUtc = DateTime.UtcNow,
            sourcePath,
            totalFiles = files.Count,
            totalBytes = files.Sum(x => x.SizeBytes),
            byCategory,
            groupedByCategoryAndMonth = grouped,
            duplicateGroupCount = duplicateGroups.Count,
            duplicateFiles,
            reclaimableBytes
        };
    }

    private static void PrintReportSummary(object report, string header)
    {
        Console.WriteLine($"== {header} ==");
        Console.WriteLine(JsonSerializer.Serialize(report, JsonOptions));
    }

    private static void PrintDuplicateHighlights(IReadOnlyList<DuplicateGroup> groups)
    {
        if (groups.Count == 0)
        {
            Console.WriteLine("No duplicates found.");
            return;
        }

        Console.WriteLine("Duplicate highlights:");
        foreach (var group in groups.Take(10))
        {
            Console.WriteLine(
                $"- Hash: {group.Hash[..12]}..., Count: {group.Files.Count}, FileSize: {FormatSize(group.SizeBytes)}");
            foreach (var file in group.Files.Take(3))
            {
                Console.WriteLine($"  {file.FullPath}");
            }
        }
    }

    private static void PrintOperationSummary(
        OperationSummary summary,
        bool dryRun,
        string source,
        string target,
        OrganizationMode mode,
        DedupeMode dedupeMode)
    {
        Console.WriteLine("== Apply summary ==");
        Console.WriteLine($"Dry run: {dryRun}");
        Console.WriteLine($"Source: {source}");
        Console.WriteLine($"Target: {target}");
        Console.WriteLine($"Mode: {mode}");
        Console.WriteLine($"Dedupe: {dedupeMode}");
        Console.WriteLine($"Scanned files: {summary.TotalFilesScanned}");
        Console.WriteLine($"Scanned bytes: {FormatSize(summary.TotalBytesScanned)}");
        Console.WriteLine($"Duplicate groups: {summary.DuplicateGroupCount}");
        Console.WriteLine($"Duplicate files: {summary.DuplicateFilesFound}");
        Console.WriteLine($"Reclaimable bytes: {FormatSize(summary.DuplicateBytesReclaimable)}");
        Console.WriteLine($"Files copied: {summary.FilesCopied}");
        Console.WriteLine($"Files moved: {summary.FilesMoved}");
        Console.WriteLine($"Duplicates quarantined: {summary.DuplicatesQuarantined}");
        Console.WriteLine($"Duplicates deleted: {summary.DuplicatesDeleted}");
        Console.WriteLine($"Errors: {summary.Errors.Count}");

        if (summary.Errors.Count > 0)
        {
            foreach (var error in summary.Errors.Take(20))
            {
                Console.WriteLine($"- {error}");
            }
        }
    }

    private static string? RequireDirectoryArg(ParsedArgs args, string key)
    {
        var rawPath = RequirePathArg(args, key);
        if (rawPath is null)
        {
            return null;
        }

        var fullPath = Path.GetFullPath(rawPath);
        if (!Directory.Exists(fullPath))
        {
            Fail($"Directory does not exist: {fullPath}");
            return null;
        }

        return fullPath;
    }

    private static string? RequirePathArg(ParsedArgs args, string key)
    {
        var value = args.GetValue(key);
        if (string.IsNullOrWhiteSpace(value))
        {
            Fail($"Missing required argument: {key}");
            return null;
        }

        return Path.GetFullPath(value);
    }

    private static OrganizationMode? ParseOrganizationMode(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return OrganizationMode.Copy;
        }

        return raw.ToLowerInvariant() switch
        {
            "copy" => OrganizationMode.Copy,
            "move" => OrganizationMode.Move,
            _ => null
        };
    }

    private static DedupeMode? ParseDedupeMode(string? raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return DedupeMode.Quarantine;
        }

        return raw.ToLowerInvariant() switch
        {
            "off" => DedupeMode.Off,
            "quarantine" => DedupeMode.Quarantine,
            "delete" => DedupeMode.Delete,
            _ => null
        };
    }

    private static void WriteReportIfRequested(ParsedArgs args, object report)
    {
        var reportPath = args.GetValue("--report");
        if (string.IsNullOrWhiteSpace(reportPath))
        {
            return;
        }

        var fullPath = Path.GetFullPath(reportPath);
        Directory.CreateDirectory(Path.GetDirectoryName(fullPath)!);
        File.WriteAllText(fullPath, JsonSerializer.Serialize(report, JsonOptions));
        Console.WriteLine($"Report written: {fullPath}");
    }

    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        var value = bytes;
        var unit = 0;

        decimal display = value;
        while (display >= 1024 && unit < units.Length - 1)
        {
            display /= 1024;
            unit++;
        }

        return $"{display:0.##} {units[unit]}";
    }

    private static ParsedArgs ParseArgs(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var flags = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        for (var i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            if (!arg.StartsWith("--", StringComparison.Ordinal))
            {
                continue;
            }

            if (i + 1 < args.Length && !args[i + 1].StartsWith("--", StringComparison.Ordinal))
            {
                values[arg] = args[i + 1];
                i++;
            }
            else
            {
                flags.Add(arg);
            }
        }

        return new ParsedArgs(values, flags);
    }

    private static int Fail(string message)
    {
        Console.Error.WriteLine($"Error: {message}");
        Console.Error.WriteLine();
        PrintUsage();
        return 1;
    }

    private static void PrintUsage()
    {
        Console.WriteLine("FileGrouper CLI");
        Console.WriteLine("Commands:");
        Console.WriteLine("  scan    --source <path> [--report <jsonPath>]");
        Console.WriteLine("  preview --source <path> [--report <jsonPath>]");
        Console.WriteLine("  apply   --source <path> --target <path> [--mode copy|move] [--dedupe off|quarantine|delete] [--dry-run] [--report <jsonPath>]");
        Console.WriteLine();
        Console.WriteLine("Examples:");
        Console.WriteLine("  FileGrouper scan --source /Volumes/USB");
        Console.WriteLine("  FileGrouper preview --source /Volumes/USB --report ./preview.json");
        Console.WriteLine("  FileGrouper apply --source /Volumes/USB --target /Volumes/USB_Organized --mode copy --dedupe quarantine --dry-run");
    }

    private sealed class ParsedArgs(
        IReadOnlyDictionary<string, string> values,
        IReadOnlySet<string> flags)
    {
        public string? GetValue(string key) => values.TryGetValue(key, out var value) ? value : null;
        public bool HasFlag(string flag) => flags.Contains(flag);
    }
}
