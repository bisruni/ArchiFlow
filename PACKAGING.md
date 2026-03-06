# Packaging and Release

This project is packaged with `setuptools` (PEP 621 metadata in `pyproject.toml`).

## Prerequisites

- Python 3.10+
- Virtual environment activated

## Build Distribution Artifacts

macOS/Linux:

```bash
bash scripts/build_dist.sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_dist.ps1
```

Output:

- `dist/*.whl`
- `dist/*.tar.gz`

## Local Install Test

```bash
python -m pip install --force-reinstall dist/*.whl
archiflow --help
```

## Upload Preparation

Use API token-based auth:

- `TWINE_USERNAME=__token__`
- `TWINE_PASSWORD=<pypi_token>`

TestPyPI upload:

```bash
TWINE_USERNAME=__token__ TWINE_PASSWORD=<token> bash scripts/publish_dist.sh testpypi
```

PyPI upload:

```bash
TWINE_USERNAME=__token__ TWINE_PASSWORD=<token> bash scripts/publish_dist.sh pypi
```
