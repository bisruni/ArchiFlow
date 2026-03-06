from __future__ import annotations

from pathlib import Path

import pytest

import archiflow.scanner as scanner_module
from archiflow.scanner import FileScanner


def test_scanner_skips_broken_symlink_without_crash(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "ok.txt").write_text("ok", encoding="utf-8")

    broken_link = source / "broken-link"
    try:
        broken_link.symlink_to(source / "missing.txt")
    except (NotImplementedError, OSError):
        pytest.skip("Symlink creation is not supported in this environment.")

    scanner = FileScanner()
    records = scanner.scan(source)

    assert [item.full_path.name for item in records] == ["ok.txt"]


def test_scanner_records_permission_error_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    blocked = source / "blocked"
    visible = source / "visible"
    blocked.mkdir(parents=True)
    visible.mkdir(parents=True)
    (blocked / "hidden.txt").write_text("x", encoding="utf-8")
    (visible / "ok.txt").write_text("ok", encoding="utf-8")

    real_scandir = scanner_module.os.scandir

    def fake_scandir(path):  # type: ignore[no-untyped-def]
        if Path(path) == blocked:
            raise PermissionError("blocked by test")
        return real_scandir(path)

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)

    errors: list[str] = []
    scanner = FileScanner()
    records = scanner.scan(source, errors=errors)

    assert [item.full_path.name for item in records] == ["ok.txt"]
    assert any("Could not read folder" in message and "blocked" in message for message in errors)
