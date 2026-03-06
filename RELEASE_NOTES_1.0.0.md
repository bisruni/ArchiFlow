# ArchiFlow 1.0.0 Release Notes

Release date: 2026-03-06

## Summary

`ArchiFlow 1.0.0` is the first stable Python release focused on:
- Safe duplicate cleanup
- Large-dataset handling
- Undoable operations and reporting
- GUI + CLI parity for common workflows

## Highlights

1. Safe duplicate management
- Default dedupe mode is quarantine.
- Every apply operation is journaled for undo/recovery.
- Duplicate cleanup and organization can run independently by scope.

2. Performance and scalability
- Multi-stage duplicate detection pipeline reduces unnecessary full hashing.
- Memory-efficient scanning and stream-friendly grouping paths.
- Hash cache supports invalidation, LRU capping, and runtime stats.

3. Reliability and trust
- Cancel/pause-aware long operations.
- Robust handling for unreadable files and interrupted runs.
- Auto-generated JSON/CSV reports on each run.

4. Packaging readiness
- Wheel and sdist builds verified.
- Twine checks integrated via build scripts.

## Compatibility

- Python: 3.10+
- OS: macOS, Linux, Windows
- GUI dependency: PySide6

## Breaking Changes / Notes

- Legacy .NET flow is no longer the primary runtime path.
- Primary runtime and tooling are Python-based (`main.py`, `archiflow` package).

## Upgrade Path

See `MIGRATION_GUIDE.md` for detailed migration steps and command mapping.

## Known Limitations

- Similar image mode depends on Pillow availability.
- Performance can vary by disk type and OS file system behavior.
