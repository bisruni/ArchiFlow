"""Command-line entry points for scanning, preview, apply and GUI launch."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path

from .config_service import AppConfig, AppConfigService
from .errors import OperationCancelledError
from .logger import configure_logging, get_logger
from .models import DedupeMode, ExecutionScope, OperationProfile, OperationProgress, OrganizationMode, ScanFilterOptions
from .pause_controller import PauseController
from .pipeline import ArchiFlowEngine, RunOptions, RunResult
from .profile_service import ProfileService
from .utils import format_size
from .validators import (
    ValidationError,
    validate_paths_separated,
    validate_similarity_max_distance,
    validate_source_path,
    validate_target_path,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI argument parser.

    Returns:
        argparse.ArgumentParser: Parser instance with subcommands.

    Example:
        >>> parser = build_parser()
        >>> parser.prog
        'archiflow'
    """
    parser = argparse.ArgumentParser(prog="archiflow", description="File grouping and duplicate cleanup")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan source and print summary")
    scan.add_argument("--source", required=True)
    scan.add_argument("--report")

    preview = sub.add_parser("preview", help="Scan + duplicate analysis")
    preview.add_argument("--source", required=True)
    preview.add_argument("--report")
    preview.add_argument("--profile")
    preview.add_argument("--similar-images", action=argparse.BooleanOptionalAction, default=None)

    apply_cmd = sub.add_parser("apply", help="Apply grouping and/or duplicate cleanup")
    apply_cmd.add_argument("--source", required=True)
    apply_cmd.add_argument("--target")
    apply_cmd.add_argument("--mode", choices=[item.value for item in OrganizationMode], default=None)
    apply_cmd.add_argument("--dedupe", choices=[item.value for item in DedupeMode], default=None)
    apply_cmd.add_argument(
        "--scope",
        choices=[item.value for item in ExecutionScope],
        default=None,
    )
    apply_cmd.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=None)
    apply_cmd.add_argument("--similar-images", action=argparse.BooleanOptionalAction, default=None)
    apply_cmd.add_argument("--profile")
    apply_cmd.add_argument("--report")

    sub.add_parser("gui", help="Open desktop GUI")
    profiles = sub.add_parser("profiles", help="List saved operation profiles")
    profiles.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute CLI command and return process exit code.

    Args:
        argv: Optional command-line argument list.

    Returns:
        int: Process exit code.

    Example:
        >>> # main(["scan", "--source", "/tmp/data"])
        >>> # Returns 0 on success.
    """
    config_service = AppConfigService()
    app_config = config_service.load_resolved_config()
    if app_config.console_log_level and not os.environ.get("ARCHIFLOW_CONSOLE_LOG_LEVEL"):
        os.environ["ARCHIFLOW_CONSOLE_LOG_LEVEL"] = app_config.console_log_level

    log_file = configure_logging(log_dir=app_config.log_dir, level=app_config.log_level or None)
    app_logger = get_logger("cli")
    app_logger.info(
        f"CLI started. config_file={config_service.config_path}",
        extra={"transaction_id": ""},
    )
    args = build_parser().parse_args(argv)
    profile_service = ProfileService()

    if args.command == "profiles":
        profiles = profile_service.load_profiles()
        if args.json:
            payload = [profile.to_dict() for profile in profiles]
            print(json.dumps(payload, ensure_ascii=True, indent=2))
        else:
            print(f"Profiles ({len(profiles)}):")
            for profile in profiles:
                default_tag = " (default)" if profile.name == app_config.default_profile else ""
                print(f"- {profile.name}{default_tag}")
        return 0

    if args.command in {None, "gui"}:
        try:
            from .gui import launch_gui
        except ModuleNotFoundError as exc:
            missing_name = getattr(exc, "name", None)
            if isinstance(missing_name, str) and missing_name.startswith("PySide6"):  # pylint: disable=no-member
                print(
                    "GUI icin PySide6 gerekli. Once bir sanal ortam acip bagimliliklari kurun:\n"
                    "  python3 -m venv .venv\n"
                    "  source .venv/bin/activate\n"
                    "  python3 -m pip install -r requirements.txt",
                    file=sys.stderr,
                )
                app_logger.error("GUI dependency missing: PySide6", extra={"transaction_id": ""})
                return 1
            raise

        app_logger.info("Launching GUI", extra={"transaction_id": ""})
        launch_gui()
        return 0

    engine = ArchiFlowEngine()
    cancel_event = threading.Event()
    pause_controller = PauseController()
    try:
        selected_profile = _resolve_profile(args, profile_service, app_config.default_profile)
    except ValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        app_logger.error(f"Profile resolution failed: {exc}", extra={"transaction_id": ""})
        return 1

    def log(message: str) -> None:
        print(message)
        app_logger.info(message, extra={"transaction_id": ""})

    def progress(item: OperationProgress) -> None:
        if item.total_files > 0:
            percent = item.processed_files / item.total_files * 100
            print(f"[{item.stage.value}] {percent:0.0f}% - {item.message}")

    # Early input validation for CLI commands
    try:
        # Validate source path (required for all commands)
        source_path = validate_source_path(args.source)

        # Determine scope to check if grouping is included
        if args.command == "scan":
            scope = ExecutionScope.GROUP_ONLY
            target_path = None
        elif args.command == "preview":
            scope = ExecutionScope.GROUP_AND_DEDUPE
            target_path = None
        else:  # apply
            scope = _resolve_apply_scope(args, selected_profile, app_config)
            # Validate target path (may be required depending on scope)
            target_path = validate_target_path(args.target, scope.includes_grouping)

        # Ensure source and target are properly separated
        validate_paths_separated(source_path, target_path)

        # Validate image similarity parameter if specified
        if getattr(args, "similar_images", False):
            validate_similarity_max_distance(10)  # Default hamming distance

    except (ValidationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        app_logger.error(f"Input validation failed: {exc}", extra={"transaction_id": ""})
        return 1

    if args.command == "scan":
        run_options = RunOptions(
            source_path=source_path,
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
        detect_similar = _resolve_preview_similar(args, selected_profile, app_config)
        run_options = RunOptions(
            source_path=source_path,
            target_path=None,
            organization_mode=OrganizationMode.COPY,
            dedupe_mode=DedupeMode.QUARANTINE,
            execution_scope=ExecutionScope.GROUP_AND_DEDUPE,
            dry_run=True,
            detect_similar_images=detect_similar,
            apply_changes=False,
            filter_options=selected_profile.filter_options if selected_profile else ScanFilterOptions(),
        )
    else:
        if selected_profile is not None:
            log(f"Profil yuklendi: {selected_profile.name}")
        run_options = RunOptions(
            source_path=source_path,
            target_path=target_path,
            organization_mode=_resolve_apply_mode(args, selected_profile, app_config),
            dedupe_mode=_resolve_apply_dedupe(args, selected_profile, app_config),
            execution_scope=scope,
            dry_run=_resolve_apply_dry_run(args, selected_profile, app_config),
            detect_similar_images=_resolve_apply_similar(args, selected_profile, app_config),
            apply_changes=True,
            filter_options=selected_profile.filter_options if selected_profile else ScanFilterOptions(),
        )

    error = engine.validate_paths(run_options.source_path, run_options.target_path, run_options.execution_scope)
    if error and run_options.apply_changes:
        print(f"Error: {error}", file=sys.stderr)
        app_logger.error(f"Path validation failed: {error}", extra={"transaction_id": ""})
        return 1

    try:
        app_logger.info(
            "Engine run started",
            extra={"transaction_id": ""},
        )
        result = engine.run(
            run_options,
            log=log,
            progress=progress,
            cancel_event=cancel_event,
            pause_controller=pause_controller,
        )
    except OperationCancelledError:
        print("Cancelled", file=sys.stderr)
        app_logger.warning("Operation cancelled", extra={"transaction_id": ""})
        return 2
    except (KeyboardInterrupt, SystemExit):
        app_logger.warning("Termination signal received", extra={"transaction_id": ""})
        raise  # Always propagate termination signals
    except Exception as exc:  # Intentionally broad for CLI error handling
        print(f"Error: {exc}", file=sys.stderr)
        app_logger.exception("Unhandled CLI error", extra={"transaction_id": ""})
        return 1

    print_summary(result)

    if getattr(args, "report", None):
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = engine.build_report(result)
        with report_path.open("w", encoding="utf-8") as stream:
            json.dump(report.to_dict(), stream, ensure_ascii=True, indent=2)
        print(f"Report written: {report_path}")
        app_logger.info(f"Report written: {report_path}", extra={"transaction_id": result.transaction_id or ""})

    app_logger.info(
        f"CLI finished. log_file={log_file}",
        extra={"transaction_id": result.transaction_id or ""},
    )

    return 0


def _resolve_profile(args: argparse.Namespace, service: ProfileService, default_name: str) -> OperationProfile | None:
    """Resolve profile from CLI argument or configured default profile name."""
    if getattr(args, "command", None) not in {"apply", "preview"}:
        return None
    requested = (getattr(args, "profile", None) or default_name or "").strip()
    if not requested:
        return None
    profiles = service.load_profiles()
    for profile in profiles:
        if profile.name.lower() == requested.lower():
            return profile
    raise ValidationError(f"Profile not found: {requested}")


def _resolve_apply_scope(
    args: argparse.Namespace, profile: OperationProfile | None, config: AppConfig
) -> ExecutionScope:
    if args.scope:
        return ExecutionScope(args.scope)
    if profile is not None:
        return profile.execution_scope
    return config.default_scope


def _resolve_apply_mode(
    args: argparse.Namespace, profile: OperationProfile | None, config: AppConfig
) -> OrganizationMode:
    if args.mode:
        return OrganizationMode(args.mode)
    if profile is not None:
        return profile.organization_mode
    return config.default_mode


def _resolve_apply_dedupe(args: argparse.Namespace, profile: OperationProfile | None, config: AppConfig) -> DedupeMode:
    if args.dedupe:
        return DedupeMode(args.dedupe)
    if profile is not None:
        return profile.dedupe_mode
    return config.default_dedupe


def _resolve_apply_dry_run(args: argparse.Namespace, profile: OperationProfile | None, config: AppConfig) -> bool:
    if args.dry_run is not None:
        return bool(args.dry_run)
    if profile is not None:
        return profile.is_dry_run
    return config.default_dry_run


def _resolve_apply_similar(args: argparse.Namespace, profile: OperationProfile | None, config: AppConfig) -> bool:
    if args.similar_images is not None:
        return bool(args.similar_images)
    if profile is not None:
        return profile.detect_similar_images
    return config.default_similar_images


def _resolve_preview_similar(args: argparse.Namespace, profile: OperationProfile | None, config: AppConfig) -> bool:
    if args.similar_images is not None:
        return bool(args.similar_images)
    if profile is not None:
        return profile.detect_similar_images
    return config.default_similar_images


def print_summary(result: RunResult) -> None:
    """Print run summary to stdout in a human-readable layout.

    Args:
        result: Completed run result to render.

    Returns:
        None
    """
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
