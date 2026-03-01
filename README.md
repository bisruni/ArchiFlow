# FileGrouper

FileGrouper can run as an Avalonia desktop app and as a CLI.
The CLI scans files, groups them by type and date, and handles duplicates safely.

## Desktop GUI

Run the desktop app:

```bash
dotnet run
```

Main workflow in GUI:

1. Language defaults to `Türkçe` (switch from top-right `Dil/Language` selector)
2. Pick `Source Folder`
3. Pick `Target Folder`
4. Choose `Organization Mode` and `Duplicate Mode`
5. Start with `Preview Analysis`
6. If results look good, turn off `Dry Run` and click `Apply Organization`

## New Advanced Features

The GUI now includes:

1. Real-time progress, pause/resume, and cancel
2. Smart filters (extensions, size, date, hidden/system toggle)
3. Undo last transaction
4. Incremental hash cache (file-based cache)
5. Similar image grouping (byte-fingerprint based)
6. Report export (`JSON`, `CSV`, `PDF`)
7. Reusable operation profiles

## Build

```bash
dotnet build
```

## CLI Commands

```bash
dotnet run -- help
```

### 1) Scan

Scans a folder and prints grouped summary.

```bash
dotnet run -- scan --source /Volumes/USB
```

### 2) Preview

Like scan, plus duplicate detection (size + SHA-256 hash).

```bash
dotnet run -- preview --source /Volumes/USB
```

### 3) Apply

Groups files into `target/<category>/<year>/<month>/...`.

```bash
dotnet run -- apply --source /Volumes/USB --target /Volumes/USB_Organized --mode copy --dedupe quarantine --dry-run
```

Remove `--dry-run` to execute.

## Options

- `--mode copy|move` (default: `copy`)
- `--dedupe off|quarantine|delete` (default: `quarantine`)
- `--report <path.json>` write JSON report
- `--dry-run` preview only, no file changes

## Safety Rules

- `--source` and `--target` cannot be the same path.
- `--target` cannot be inside `--source`.
- Duplicate handling keeps one file and processes the rest.
- In `quarantine` mode, duplicates are moved under:
  `SOURCE/Duplicates_Quarantine/<timestamp>/...`
