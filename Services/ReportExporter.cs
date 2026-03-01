using FileGrouper.Models;
using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace FileGrouper.Services;

public sealed class ReportExporter
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public (string JsonPath, string CsvPath, string PdfPath) Export(OperationReportData report, string outputDirectory)
    {
        Directory.CreateDirectory(outputDirectory);
        var stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss", CultureInfo.InvariantCulture);

        var jsonPath = Path.Combine(outputDirectory, $"report_{stamp}.json");
        var csvPath = Path.Combine(outputDirectory, $"report_{stamp}.csv");
        var pdfPath = Path.Combine(outputDirectory, $"report_{stamp}.pdf");

        File.WriteAllText(jsonPath, JsonSerializer.Serialize(report, JsonOptions));
        File.WriteAllText(csvPath, BuildCsv(report), Encoding.UTF8);
        WriteSimplePdf(BuildPdfText(report), pdfPath);

        return (jsonPath, csvPath, pdfPath);
    }

    private static string BuildCsv(OperationReportData report)
    {
        var sb = new StringBuilder();
        sb.AppendLine("Metric,Value");
        sb.AppendLine($"GeneratedAtUtc,{report.GeneratedAtUtc:O}");
        sb.AppendLine($"SourcePath,\"{EscapeCsv(report.SourcePath)}\"");
        sb.AppendLine($"TargetPath,\"{EscapeCsv(report.TargetPath)}\"");
        sb.AppendLine($"TotalFiles,{report.Summary.TotalFilesScanned}");
        sb.AppendLine($"TotalBytes,{report.Summary.TotalBytesScanned}");
        sb.AppendLine($"DuplicateGroups,{report.Summary.DuplicateGroupCount}");
        sb.AppendLine($"DuplicateFiles,{report.Summary.DuplicateFilesFound}");
        sb.AppendLine($"SimilarImageGroups,{report.SimilarImageGroups.Count}");
        sb.AppendLine($"ReclaimableBytes,{report.Summary.DuplicateBytesReclaimable}");
        sb.AppendLine($"FilesCopied,{report.Summary.FilesCopied}");
        sb.AppendLine($"FilesMoved,{report.Summary.FilesMoved}");
        sb.AppendLine($"DuplicatesQuarantined,{report.Summary.DuplicatesQuarantined}");
        sb.AppendLine($"DuplicatesDeleted,{report.Summary.DuplicatesDeleted}");
        sb.AppendLine($"Errors,{report.Summary.Errors.Count}");
        sb.AppendLine();
        sb.AppendLine("DuplicateHash,FileSize,FilePath");

        foreach (var group in report.DuplicateGroups)
        {
            foreach (var file in group.Files)
            {
                sb.AppendLine($"{group.Hash},{group.SizeBytes},\"{EscapeCsv(file.FullPath)}\"");
            }
        }

        return sb.ToString();
    }

    private static string BuildPdfText(OperationReportData report)
    {
        var sb = new StringBuilder();
        sb.AppendLine("FileGrouper Report");
        sb.AppendLine($"Generated: {report.GeneratedAtUtc:yyyy-MM-dd HH:mm:ss} UTC");
        sb.AppendLine($"Source: {report.SourcePath}");
        sb.AppendLine($"Target: {report.TargetPath}");
        sb.AppendLine($"Total Files: {report.Summary.TotalFilesScanned}");
        sb.AppendLine($"Total Size: {FormatSize(report.Summary.TotalBytesScanned)}");
        sb.AppendLine($"Duplicate Groups: {report.Summary.DuplicateGroupCount}");
        sb.AppendLine($"Duplicate Files: {report.Summary.DuplicateFilesFound}");
        sb.AppendLine($"Similar Image Groups: {report.SimilarImageGroups.Count}");
        sb.AppendLine($"Reclaimable: {FormatSize(report.Summary.DuplicateBytesReclaimable)}");
        sb.AppendLine($"Copied: {report.Summary.FilesCopied}");
        sb.AppendLine($"Moved: {report.Summary.FilesMoved}");
        sb.AppendLine($"Quarantined: {report.Summary.DuplicatesQuarantined}");
        sb.AppendLine($"Deleted: {report.Summary.DuplicatesDeleted}");
        sb.AppendLine($"Errors: {report.Summary.Errors.Count}");
        sb.AppendLine();
        sb.AppendLine("Top Duplicate Groups:");
        foreach (var group in report.DuplicateGroups.Take(10))
        {
            sb.AppendLine($"- {group.Hash[..12]}... ({group.Files.Count} files, {FormatSize(group.SizeBytes)})");
        }

        if (report.SimilarImageGroups.Count > 0)
        {
            sb.AppendLine();
            sb.AppendLine("Similar Image Groups:");
            foreach (var group in report.SimilarImageGroups.Take(10))
            {
                sb.AppendLine($"- {group.AnchorPath} (+{group.SimilarPaths.Count} similar)");
            }
        }

        return sb.ToString();
    }

    private static void WriteSimplePdf(string text, string path)
    {
        // Minimal single-page PDF writer for plain text.
        var safeText = EscapePdf(text);
        var content = $"BT /F1 10 Tf 40 800 Td 12 TL ({safeText.Replace("\n", ") Tj T* (")}) Tj ET";

        var objects = new[]
        {
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
            "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
            $"5 0 obj << /Length {Encoding.ASCII.GetByteCount(content)} >> stream\n{content}\nendstream endobj"
        };

        using var stream = new MemoryStream();
        using var writer = new StreamWriter(stream, Encoding.ASCII, leaveOpen: true);
        writer.Write("%PDF-1.4\n");
        writer.Flush();

        var offsets = new int[objects.Length + 1];
        for (var i = 0; i < objects.Length; i++)
        {
            offsets[i + 1] = (int)stream.Position;
            writer.Write(objects[i]);
            writer.Write('\n');
            writer.Flush();
        }

        var xrefPos = (int)stream.Position;
        writer.Write($"xref\n0 {objects.Length + 1}\n");
        writer.Write("0000000000 65535 f \n");
        for (var i = 1; i <= objects.Length; i++)
        {
            writer.Write($"{offsets[i]:0000000000} 00000 n \n");
        }

        writer.Write($"trailer << /Size {objects.Length + 1} /Root 1 0 R >>\n");
        writer.Write($"startxref\n{xrefPos}\n%%EOF");
        writer.Flush();

        File.WriteAllBytes(path, stream.ToArray());
    }

    private static string EscapeCsv(string value)
    {
        return value.Replace("\"", "\"\"", StringComparison.Ordinal);
    }

    private static string EscapePdf(string value)
    {
        return value
            .Replace("\\", "\\\\", StringComparison.Ordinal)
            .Replace("(", "\\(", StringComparison.Ordinal)
            .Replace(")", "\\)", StringComparison.Ordinal)
            .Replace("\r", string.Empty, StringComparison.Ordinal);
    }

    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        decimal display = bytes;
        var unit = 0;

        while (display >= 1024 && unit < units.Length - 1)
        {
            display /= 1024;
            unit++;
        }

        return $"{display:0.##} {units[unit]}";
    }
}
