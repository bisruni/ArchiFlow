from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from archiflow.gui import MainWindow, qdarktheme
from archiflow.gui_theme import apply_gui_theme


def _render_and_save(window: MainWindow, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    QApplication.processEvents()
    time.sleep(0.05)
    QApplication.processEvents()
    if not window.grab().save(str(output), "PNG"):
        raise RuntimeError(f"Failed to save screenshot: {output}")


def _capture_state(window: MainWindow, output: Path, prepare: Callable[[], None]) -> None:
    prepare()
    _render_and_save(window, output)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication(sys.argv)
    app.setFont(QFont("SF Pro Text", 11))
    apply_gui_theme(app, qdarktheme)

    out_dir = Path("assets/marketing/screenshots").resolve()
    window = MainWindow()
    window.resize(1440, 920)
    window.show()
    QApplication.processEvents()

    window.source_edit.setText("/Volumes/ExternalDrive")
    window.target_edit.setText("/Volumes/ExternalDrive_Organized")

    _capture_state(
        window,
        out_dir / "01-dashboard.png",
        lambda: (
            window.workflow_tabs.setCurrentIndex(0),
            window.tabs.setCurrentIndex(0),
        ),
    )
    _capture_state(
        window,
        out_dir / "02-duplicate-analysis.png",
        lambda: (
            window.workflow_tabs.setCurrentIndex(1),
            window.tabs.setCurrentIndex(0),
        ),
    )
    _capture_state(
        window,
        out_dir / "03-logs-and-undo.png",
        lambda: (
            window.workflow_tabs.setCurrentIndex(2),
            window.tabs.setCurrentIndex(1),
        ),
    )

    print(f"[screenshots] generated under {out_dir}")
    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
