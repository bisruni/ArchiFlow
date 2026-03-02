from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from .errors import OperationCancelledError
from .models import DedupeMode, ExecutionScope, OrganizationMode, ScanFilterOptions
from .pause_controller import PauseController
from .pipeline import FileGrouperEngine, RunOptions
from .utils import format_size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="filegrouper", description="File grouping and duplicate cleanup")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan source and print summary")
    scan.add_argument("--source", required=True)
    scan.add_argument("--report")

    preview = sub.add_parser("preview", help="Scan + duplicate analysis")
    preview.add_argument("--source", required=True)
    preview.add_argument("--report")

    apply_cmd = sub.add_parser("apply", help="Apply grouping and/or duplicate cleanup")
    apply_cmd.add_argument("--source", required=True)
    apply_cmd.add_argument("--target")
    apply_cmd.add_argument("--mode", choices=[item.value for item in OrganizationMode], default=OrganizationMode.COPY.value)
    apply_cmd.add_argument("--dedupe", choices=[item.value for item in DedupeMode], default=DedupeMode.QUARANTINE.value)
    apply_cmd.add_argument(
        "--scope",
        choices=[item.value for item in ExecutionScope],
        default=ExecutionScope.GROUP_AND_DEDUPE.value,
    )
    apply_cmd.add_argument("--dry-run", action="store_true")
    apply_cmd.add_argument("--similar-images", action="store_true")
    apply_cmd.add_argument("--report")

    sub.add_parser("gui", help="Open desktop GUI")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {None, "gui"}:
        try:
            from .gui import launch_gui
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("PySide6"):
                print(
                    "GUI icin PySide6 gerekli. Once bir sanal ortam acip bagimliliklari kurun:\n"
                    "  python3 -m venv .venv\n"
                    "  source .venv/bin/activate\n"
                    "  python3 -m pip install -r requirements.txt",
                    file=sys.stderr,
                )
                return 1
            raise

        launch_gui()
        return 0

    engine = FileGrouperEngine()
    cancel_event = threading.Event()
    pause_controller = PauseController()

    def log(message: str) -> None:
        print(message)

    def progress(item) -> None:
        if item.total_files > 0:
            percent = item.processed_files / item.total_files * 100
            print(f"[{item.stage.value}] {percent:0.0f}% - {item.message}")

    if args.command == "scan":
        run_options = RunOptions(
            source_path=Path(args.source),
            target_path=None,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=DedupeMode.OFF,
            execution_scope=ExecutionScope.GROUP_ONLY,
            dry_run=True,
            detect_similar_images=False,
            apply_changes=False,
            filter_options=ScanFilterOptions(),
        )
    elif args.command == "preview":
        run_options = RunOptions(
            source_path=Path(args.source),
            target_path=None,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=DedupeMode.QUARANTINE,
            execution_scope=ExecutionScope.GROUP_AND_DEDUPE,
            dry_run=True,
            detect_similar_images=False,
            apply_changes=False,
            filter_options=ScanFilterOptions(),
        )
    else:
        run_options = RunOptions(
            source_path=Path(args.source),
            target_path=Path(args.target).expanduser() if args.target else None,
            organization_mode=OrganizationMode(args.mode),
            dedupe_mode=DedupeMode(args.dedupe),
            execution_scope=ExecutionScope(args.scope),
            dry_run=bool(args.dry_run),
            detect_similar_images=bool(args.similar_images),
            apply_changes=True,
            filter_options=ScanFilterOptions(),
        )

    error = engine.validate_paths(run_options.source_path, run_options.target_path, run_options.execution_scope)
    if error and run_options.apply_changes:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        result = engine.run(
            run_options,
            log=log,
            progress=progress,
            cancel_event=cancel_event,
            pause_controller=pause_controller,
        )
    except OperationCancelledError:
        print("Cancelled", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_summary(result)

    if getattr(args, "report", None):
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = engine.build_report(result)
        with report_path.open("w", encoding="utf-8") as stream:
            json.dump(report.to_dict(), stream, ensure_ascii=True, indent=2)
        print(f"Report written: {report_path}")

    return 0


def print_summary(result) -> None:
    summary = result.summary
    print("== Summary ==")
    print(f"Source: {result.source_path}")
    print(f"Target: {result.target_path}")
    print(f"Scanned files: {summary.total_files_scanned}")
    print(f"Scanned size: {format_size(summary.total_bytes_scanned)}")
    print(f"Duplicate groups: {summary.duplicate_group_count}")
    print(f"Duplicate files: {summary.duplicate_files_found}")
    print(f"Reclaimable: {format_size(summary.duplicate_bytes_reclaimable)}")
    print(f"Copied: {summary.files_copied}")
    print(f"Moved: {summary.files_moved}")
    print(f"Quarantined: {summary.duplicates_quarantined}")
    print(f"Deleted duplicates: {summary.duplicates_deleted}")
    print(f"Errors: {len(summary.errors)}")


if __name__ == "__main__":
    raise SystemExit(main())
