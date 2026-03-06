# ArchiFlow

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](./tests)
[![Coverage](https://img.shields.io/badge/coverage-htmlcov-blue)](./htmlcov/index.html)
[![Lint](https://img.shields.io/badge/lint-passing-success)](./tox.ini)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

ArchiFlow is a desktop + CLI tool for large-scale file cleanup:

- Safe duplicate detection (`size -> quick signature -> SHA-256 -> byte verify`)
- Type/date-based file organization
- Default-safe quarantine flow with undoable transaction journal
- Performance-aware pipeline for large folders and external disks

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 main.py gui
```

Default mode is safe preview + quarantine-oriented workflow.

## Core Commands

```bash
# Help
python3 main.py -h

# Scan summary only
python3 main.py scan --source /Volumes/USB

# Preview analysis (no filesystem mutation)
python3 main.py preview --source /Volumes/USB

# Apply operations (remove --dry-run for real execution)
python3 main.py apply \
  --source /Volumes/USB \
  --target /Volumes/USB_Organized \
  --scope group_and_dedupe \
  --mode copy \
  --dedupe quarantine \
  --dry-run
```

## Safety Model

- Deletion is never the default path.
- Quarantine location: `TARGET/.archiflow_quarantine/<timestamp>/`
- Every mutation is journaled in `.archiflow/transactions/`
- Undo works from journal entries (reverse order, partial-failure tolerant).
- Similar-image detection is report-only and disabled by default.

## GUI Workflow

1. Select source folder.
2. Select target folder (required for organization scope).
3. Pick workflow tab: all / duplicate-only / organize-only.
4. Run preview and validate summary card.
5. Review duplicate groups (double-click row to open file location).
6. Confirm apply summary dialog.
7. Use undo or open quarantine folder when needed.

## Documentation Map

### User Documentation

- [Main Sphinx index](./docs/index.rst)
- [Installation](./docs/user-guide/installation.rst)
- [Quick start](./docs/user-guide/quick-start.rst)
- [GUI walkthrough](./docs/user-guide/gui-walkthrough.rst)
- [CLI reference](./docs/user-guide/cli-reference.rst)
- [Configuration](./docs/user-guide/configuration.rst)
- [Tutorials](./docs/tutorials/index.rst)
- [Examples and troubleshooting](./docs/examples/index.rst)

### Developer Documentation

- [Architecture overview](./docs/development/architecture-overview.rst)
- [Algorithm explanations](./docs/development/algorithm-explanations.rst)
- [Development setup](./docs/development/development-setup.rst)
- [Testing guidelines](./docs/development/testing-guidelines.rst)
- [Performance baselines](./docs/development/phase8-performance-baselines.rst)
- [API docs](./docs/api/index.rst)

### Release and Operations Docs

- [Packaging guide](./PACKAGING.md)
- [Changelog](./CHANGELOG.md)
- [Release notes 1.0.0](./RELEASE_NOTES_1.0.0.md)
- [Migration guide](./MIGRATION_GUIDE.md)
- [Dependency license report](./DEPENDENCY_LICENSES.md)
- [Marketing assets](./MARKETING.md)
- [Contributing](./CONTRIBUTING.md)

## Build Docs

```bash
python3 -m pip install -e .[dev]
make -C docs html
python scripts/docs_self_check.py
```

Output: `docs/_build/html/`

## Quality Gates

```bash
tox -e format
tox -e lint
tox -e type
tox -e py313
pytest -q
```

## Performance Benchmark

```bash
python tests/performance/run_benchmark.py \
  --source /tmp/archiflow_perf \
  --generate \
  --files 5000 \
  --duplicate-ratio 0.2 \
  --same-size-ratio 0.1 \
  --iterations 2
```

## Packaging

```bash
bash scripts/build_dist.sh
```

Artifacts are written to `dist/` (wheel + sdist).

## Legal Checks

```bash
source .venv/bin/activate
python scripts/verify_licenses.py
```

License verification output is written to `DEPENDENCY_LICENSES.md`.
