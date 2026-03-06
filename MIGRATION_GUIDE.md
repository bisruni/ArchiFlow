# Migration Guide

This guide helps migrate from pre-1.0/legacy setup to `ArchiFlow 1.0.0`.

## 1. Runtime Migration

Old approach:
- Legacy/experimental runtime variants (including older .NET-oriented flow)

New approach:
- Python runtime only:
  - `python3 main.py gui`
  - `python3 main.py scan --source <path>`
  - `python3 main.py preview --source <path>`
  - `python3 main.py apply --source <path> --target <path> ...`

## 2. Naming Migration

- Project/app naming is standardized as `ArchiFlow`.
- Python package/CLI entry point remains `archiflow` for compatibility.

## 3. Config Migration

New default config path:
- `./.archiflow/config.yaml`

Recommended:
1. Start once to auto-create defaults.
2. Re-apply your preferred defaults (`scope`, `mode`, `dedupe`, `dry_run`).
3. Optionally set:
   - `ARCHIFLOW_CONFIG_FILE`
   - `ARCHIFLOW_PROFILE_PATH`

## 4. Dedupe Behavior Migration

Behavior in 1.0.0:
- Default dedupe mode is `quarantine`.
- `delete` is explicit and never implicit.
- Similar image mode reports candidates; it is not a direct delete operation.

## 5. Transaction and Undo Migration

1.0.0 introduces stronger transaction journaling:
- Journal location: `TARGET/.archiflow/transactions/`
- Undo operates from latest transaction log.

Action:
- Keep transaction files if you want reliable rollback capability.

## 6. Reporting Migration

Automatic reports:
- `TARGET/.archiflow/reports/*.json`
- `TARGET/.archiflow/reports/*.csv`

If you had custom report parsing, update to 1.0.0 summary/field layout.

## 7. Packaging Migration

Build now uses standard Python packaging:
- `bash scripts/build_dist.sh`
- `dist/*.whl` and `dist/*.tar.gz`

## 8. Verification Checklist

After migration:
1. Run `python3 main.py preview --source <path>`.
2. Confirm summary/report output.
3. Run an apply on test data with quarantine mode.
4. Validate undo on that transaction.
