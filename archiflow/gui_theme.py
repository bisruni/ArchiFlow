"""GUI theme helpers."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

FALLBACK_STYLESHEET = """
QWidget { background: #f6f7f9; color: #111827; font-size: 12px; }
QGroupBox { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #6b7280; }
QLineEdit, QComboBox, QSpinBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    padding: 8px 10px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {
    border: 1px solid #2563eb;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    padding: 9px 14px;
}
QPushButton:hover { background: #f3f4f6; }
QPushButton:pressed { background: #e5e7eb; }
QPushButton:disabled { color: #9ca3af; border-color: #e5e7eb; background: #f9fafb; }

QProgressBar {
    background: #eef2f7;
    border: 1px solid #e5e7eb;
    border-radius: 9px;
    text-align: center;
    height: 18px;
}
QProgressBar::chunk {
    background: #2563eb;
    border-radius: 9px;
}

QTabWidget::pane { border: 1px solid #e5e7eb; border-radius: 10px; background: #ffffff; }
QTabBar::tab {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-bottom: none;
    padding: 10px 14px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    color: #374151;
    margin-right: 6px;
}
QTabBar::tab:selected { background: #ffffff; color: #111827; }

QHeaderView::section {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    padding: 8px 10px;
    color: #374151;
    font-weight: 600;
}
QTableWidget {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    gridline-color: #f1f5f9;
    selection-background-color: #dbeafe;
    selection-color: #111827;
}
QTextEdit {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 10px;
}
"""


def apply_gui_theme(app: QApplication, qdarktheme_module: Any | None) -> None:
    """Apply the best available light theme to the Qt application.

    Args:
        app: Qt application instance.
        qdarktheme_module: Imported `qdarktheme` module or ``None``.

    Returns:
        None

    Example:
        >>> # apply_gui_theme(app, qdarktheme)
        >>> # Uses qdarktheme when available, otherwise fallback stylesheet.
    """
    themed = False
    if qdarktheme_module is not None:
        for fn_name in ("setup_theme", "load_stylesheet"):
            fn = getattr(qdarktheme_module, fn_name, None)
            if callable(fn):
                try:
                    if fn_name == "setup_theme":
                        fn("light")
                    else:
                        css = fn(theme="light") if "theme" in fn.__code__.co_varnames else fn()
                        if isinstance(css, str) and css.strip():
                            app.setStyleSheet(css)
                    themed = True
                    break
                except (AttributeError, TypeError, ValueError):
                    pass

    if not themed:
        app.setStyleSheet(FALLBACK_STYLESHEET)
