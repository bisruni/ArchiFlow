from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import OperationReportData
from .utils import format_size


class ReportExporter:
    def export(self, report: OperationReportData, output_directory: Path) -> tuple[Path, Path, Path]:
        output_directory.mkdir(parents=True, exist_ok=True)
        stamp = report.generated_at_utc.astimezone().strftime("%Y%m%d_%H%M%S")

        json_path = output_directory / f"report_{stamp}.json"
        csv_path = output_directory / f"report_{stamp}.csv"
        pdf_path = output_directory / f"report_{stamp}.pdf"

        with json_path.open("w", encoding="utf-8") as stream:
            json.dump(report.to_dict(), stream, ensure_ascii=True, indent=2)

        self._write_csv(report, csv_path)
        self._write_simple_pdf(self._build_pdf_text(report), pdf_path)
        return json_path, csv_path, pdf_path

    def _write_csv(self, report: OperationReportData, path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Metric", "Value"])
            writer.writerow(["GeneratedAtUtc", report.generated_at_utc.isoformat()])
            writer.writerow(["TransactionId", report.transaction_id or ""])
            writer.writerow(["SourcePath", str(report.source_path)])
            writer.writerow(["TargetPath", str(report.target_path)])
            writer.writerow(["TotalFiles", report.summary.total_files_scanned])
            writer.writerow(["TotalBytes", report.summary.total_bytes_scanned])
            writer.writerow(["DuplicateGroups", report.summary.duplicate_group_count])
            writer.writerow(["DuplicateFiles", report.summary.duplicate_files_found])
            writer.writerow(["SimilarImageGroups", len(report.similar_image_groups)])
            writer.writerow(["SkippedFiles", len(report.summary.skipped_files)])
            writer.writerow(["ReclaimableBytes", report.summary.duplicate_bytes_reclaimable])
            writer.writerow(["FilesCopied", report.summary.files_copied])
            writer.writerow(["FilesMoved", report.summary.files_moved])
            writer.writerow(["DuplicatesQuarantined", report.summary.duplicates_quarantined])
            writer.writerow(["DuplicatesDeleted", report.summary.duplicates_deleted])
            writer.writerow(["Errors", len(report.summary.errors)])
            writer.writerow([])
            writer.writerow(["DuplicateHash", "FileSize", "FilePath"])

            for group in report.duplicate_groups:
                for item in group.files:
                    writer.writerow([group.sha256_hash, group.size_bytes, str(item.full_path)])

            if report.summary.skipped_files:
                writer.writerow([])
                writer.writerow(["SkippedFilePath"])
                for item in report.summary.skipped_files:
                    writer.writerow([item])

            if report.summary.errors:
                writer.writerow([])
                writer.writerow(["Error"])
                for item in report.summary.errors:
                    writer.writerow([item])

    def _build_pdf_text(self, report: OperationReportData) -> str:
        lines: list[str] = [
            "ArchiFlow Report",
            f"Generated: {report.generated_at_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"Transaction ID: {report.transaction_id or '-'}",
            f"Source: {report.source_path}",
            f"Target: {report.target_path}",
            f"Total Files: {report.summary.total_files_scanned}",
            f"Total Size: {format_size(report.summary.total_bytes_scanned)}",
            f"Duplicate Groups: {report.summary.duplicate_group_count}",
            f"Duplicate Files: {report.summary.duplicate_files_found}",
            f"Similar Image Groups: {len(report.similar_image_groups)}",
            f"Skipped Files: {len(report.summary.skipped_files)}",
            f"Reclaimable: {format_size(report.summary.duplicate_bytes_reclaimable)}",
            f"Copied: {report.summary.files_copied}",
            f"Moved: {report.summary.files_moved}",
            f"Quarantined: {report.summary.duplicates_quarantined}",
            f"Deleted: {report.summary.duplicates_deleted}",
            f"Errors: {len(report.summary.errors)}",
            "",
            "Top Duplicate Groups:",
        ]

        for group in report.duplicate_groups[:10]:
            lines.append(f"- {group.sha256_hash[:12]}... ({len(group.files)} files, {format_size(group.size_bytes)})")

        if report.similar_image_groups:
            lines.append("")
            lines.append("Similar Image Groups:")
            for group in report.similar_image_groups[:10]:
                lines.append(f"- {group.anchor_path} (+{len(group.similar_paths)} similar)")

        return "\n".join(lines)

    def _write_simple_pdf(self, text: str, path: Path) -> None:
        escaped = (
            text.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\r", "")
        )
        content = f"BT /F1 10 Tf 40 800 Td 12 TL ({escaped.replace(chr(10), ') Tj T* (')}) Tj ET"
        content_bytes = content.encode("ascii", errors="replace")

        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
            f"5 0 obj << /Length {len(content_bytes)} >> stream\n".encode("ascii") + content_bytes + b"\nendstream endobj\n",
        ]

        buffer = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(buffer))
            buffer.extend(obj)

        xref_pos = len(buffer)
        buffer.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        buffer.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            buffer.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        buffer.extend(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii"))
        buffer.extend(f"startxref\n{xref_pos}\n%%EOF".encode("ascii"))

        path.write_bytes(buffer)
