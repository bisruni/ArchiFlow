using FileGrouper.Models;
using System;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace FileGrouper.Services;

public sealed class TransactionService
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true
    };

    public string SaveTransaction(OperationTransaction transaction)
    {
        var txRoot = Path.Combine(transaction.TargetRoot, ".filegrouper", "transactions");
        Directory.CreateDirectory(txRoot);
        var path = Path.Combine(txRoot, $"{transaction.CreatedAtUtc:yyyyMMdd_HHmmss}_{transaction.TransactionId}.json");
        File.WriteAllText(path, JsonSerializer.Serialize(transaction, JsonOptions));
        return path;
    }

    public string? FindLatestTransactionFile(string targetRoot)
    {
        var txRoot = Path.Combine(targetRoot, ".filegrouper", "transactions");
        if (!Directory.Exists(txRoot))
        {
            return null;
        }

        return Directory.EnumerateFiles(txRoot, "*.json")
            .OrderByDescending(File.GetCreationTimeUtc)
            .FirstOrDefault();
    }

    public OperationTransaction Load(string filePath)
    {
        var json = File.ReadAllText(filePath);
        return JsonSerializer.Deserialize<OperationTransaction>(json)
               ?? throw new InvalidOperationException($"Could not parse transaction file: {filePath}");
    }

    public OperationSummary UndoLastTransaction(string targetRoot, Action<string>? log = null)
    {
        var latest = FindLatestTransactionFile(targetRoot);
        if (string.IsNullOrWhiteSpace(latest))
        {
            throw new InvalidOperationException("No transaction file found for undo.");
        }

        return UndoTransaction(latest, log);
    }

    public OperationSummary UndoTransaction(string transactionFilePath, Action<string>? log = null)
    {
        var transaction = Load(transactionFilePath);
        var summary = new OperationSummary();

        foreach (var entry in transaction.Entries.AsEnumerable().Reverse())
        {
            try
            {
                switch (entry.Action)
                {
                    case TransactionAction.Copied:
                        if (File.Exists(entry.DestinationPath))
                        {
                            File.Delete(entry.DestinationPath);
                            summary.FilesCopied++;
                        }
                        break;

                    case TransactionAction.Moved:
                        if (File.Exists(entry.DestinationPath))
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(entry.SourcePath)!);
                            File.Move(entry.DestinationPath, entry.SourcePath);
                            summary.FilesMoved++;
                        }
                        break;

                    case TransactionAction.QuarantinedDuplicate:
                        if (File.Exists(entry.DestinationPath))
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(entry.SourcePath)!);
                            File.Move(entry.DestinationPath, entry.SourcePath);
                            summary.DuplicatesQuarantined++;
                        }
                        break;

                    case TransactionAction.DeletedDuplicate:
                        // Hard delete cannot be restored automatically.
                        summary.DuplicatesDeleted++;
                        log?.Invoke($"Skipped deleted duplicate restore: {entry.SourcePath}");
                        break;
                }
            }
            catch (Exception ex)
            {
                summary.Errors.Add($"Undo failed for '{entry.SourcePath}': {ex.Message}");
            }
        }

        return summary;
    }
}
