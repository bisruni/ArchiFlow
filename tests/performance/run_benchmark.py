from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from archiflow.models import ExecutionScope
from tests.performance.perf_utils import compare_with_baseline, generate_perf_dataset, run_preview_benchmark, save_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ArchiFlow performance benchmark suite.")
    parser.add_argument("--source", required=True, help="Dataset source folder.")
    parser.add_argument("--generate", action="store_true", help="Generate dataset into source folder before running.")
    parser.add_argument("--files", type=int, default=5000, help="File count for dataset generation.")
    parser.add_argument("--duplicate-ratio", type=float, default=0.2, help="Exact duplicate file ratio.")
    parser.add_argument("--same-size-ratio", type=float, default=0.1, help="Same-size different-content file ratio.")
    parser.add_argument(
        "--scope",
        choices=[item.value for item in ExecutionScope],
        default=ExecutionScope.GROUP_AND_DEDUPE.value,
        help="Execution scope for preview benchmark.",
    )
    parser.add_argument("--iterations", type=int, default=1, help="Benchmark iteration count.")
    parser.add_argument(
        "--output",
        default="tests/performance/latest_benchmark.json",
        help="Output JSON path for benchmark result.",
    )
    parser.add_argument("--baseline", help="Optional baseline JSON file for regression detection.")
    parser.add_argument(
        "--max-time-regression", type=float, default=1.2, help="Allowed avg time regression multiplier."
    )
    parser.add_argument(
        "--max-memory-regression",
        type=float,
        default=1.2,
        help="Allowed avg memory regression multiplier.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.source).expanduser().resolve()

    dataset_stats: dict[str, int] | None = None
    if args.generate:
        stats = generate_perf_dataset(
            source,
            files=args.files,
            duplicate_ratio=args.duplicate_ratio,
            same_size_ratio=args.same_size_ratio,
        )
        dataset_stats = {
            "files_created": stats.files_created,
            "bytes_written": stats.bytes_written,
            "duplicate_files": stats.duplicate_files,
            "same_size_variant_files": stats.same_size_variant_files,
        }

    benchmark = run_preview_benchmark(
        source=source,
        iterations=args.iterations,
        execution_scope=ExecutionScope(args.scope),
    )
    payload = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "source": str(source),
        "dataset": dataset_stats,
        "benchmark": benchmark,
    }
    output = Path(args.output).expanduser().resolve()
    save_json(output, payload)

    print(f"[perf] output={output}")
    print(f"[perf] scope={args.scope}")
    print(
        "[perf] elapsed_avg="
        f"{benchmark['elapsed_seconds']['avg']:.3f}s "
        f"peak_mem_avg={benchmark['peak_memory_bytes']['avg'] / (1024 * 1024):.2f}MB"
    )
    print(
        "[perf] throughput="
        f"{benchmark['files_per_second']['avg']:.1f} files/s "
        f"{benchmark['bytes_per_second']['avg'] / (1024 * 1024):.2f} MB/s"
    )
    if "peak_rss_bytes" in benchmark:
        print(f"[perf] peak_rss_avg={benchmark['peak_rss_bytes']['avg'] / (1024 * 1024):.2f}MB")
    summary = benchmark["summary"]
    print(
        "[perf] scanned="
        f"{summary['total_files_scanned']} dup_groups={summary['duplicate_group_count']} "
        f"dup_files={summary['duplicate_files_found']} reclaimable={summary['duplicate_bytes_reclaimable']}"
    )

    if args.baseline:
        baseline_path = Path(args.baseline).expanduser().resolve()
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_benchmark = baseline_payload["benchmark"]
        issues = compare_with_baseline(
            benchmark,
            baseline_benchmark,
            max_time_regression=args.max_time_regression,
            max_memory_regression=args.max_memory_regression,
        )
        if issues:
            print("[perf] regression detected:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print("[perf] regression check: PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
