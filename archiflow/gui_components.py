"""GUI dialogs and worker object extracted from the main window module."""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .errors import OperationCancelledError
from .gui_texts import TR
from .models import DuplicateGroup
from .pause_controller import PauseController
from .pipeline import ArchiFlowEngine, RunOptions
from .utils import format_size


@dataclass
class UiFilterDraft:
    """Mutable in-memory values used by filter-editing UI."""

    include_ext: str = ""
    exclude_ext: str = ""
    min_mb: str = ""
    max_mb: str = ""
    from_date: str = ""  # YYYY-MM-DD
    to_date: str = ""  # YYYY-MM-DD


class FiltersDialog(QDialog):
    """Modal dialog for editing scan filter values."""

    def __init__(self, parent: QWidget, draft: UiFilterDraft) -> None:
        """Create filter dialog and prefill fields from draft values.

        Args:
            parent: Parent widget.
            draft: Existing filter values to load into input fields.
        """
        super().__init__(parent)
        self.setWindowTitle("Filtreler")
        self.setModal(True)
        self.setMinimumWidth(520)

        self.filter_result: UiFilterDraft | None = None

        self.include = QLineEdit(draft.include_ext)
        self.exclude = QLineEdit(draft.exclude_ext)
        self.min_mb = QLineEdit(draft.min_mb)
        self.max_mb = QLineEdit(draft.max_mb)
        self.from_date = QLineEdit(draft.from_date)
        self.to_date = QLineEdit(draft.to_date)

        form = QGridLayout()
        r = 0
        form.addWidget(QLabel("Sadece uzantılar (örn: jpg,png,mp4)"), r, 0)
        form.addWidget(self.include, r, 1)
        r += 1
        form.addWidget(QLabel("Hariç uzantılar (örn: tmp,ds_store)"), r, 0)
        form.addWidget(self.exclude, r, 1)
        r += 1
        form.addWidget(QLabel("Min boyut (MB)"), r, 0)
        form.addWidget(self.min_mb, r, 1)
        r += 1
        form.addWidget(QLabel("Max boyut (MB)"), r, 0)
        form.addWidget(self.max_mb, r, 1)
        r += 1
        form.addWidget(QLabel("Başlangıç (YYYY-AA-GG)"), r, 0)
        form.addWidget(self.from_date, r, 1)
        r += 1
        form.addWidget(QLabel("Bitiş (YYYY-AA-GG)"), r, 0)
        form.addWidget(self.to_date, r, 1)

        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        cancel = QPushButton("Vazgeç")
        save = QPushButton("Kaydet")
        save.setDefault(True)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)

        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)

        root = QVBoxLayout()
        root.addLayout(form)
        root.addSpacing(10)
        root.addLayout(btn_row)
        self.setLayout(root)

    @Slot()
    def _save(self) -> None:
        """Collect values from inputs and accept dialog."""
        self.filter_result = UiFilterDraft(
            include_ext=self.include.text().strip(),
            exclude_ext=self.exclude.text().strip(),
            min_mb=self.min_mb.text().strip(),
            max_mb=self.max_mb.text().strip(),
            from_date=self.from_date.text().strip(),
            to_date=self.to_date.text().strip(),
        )
        self.accept()


class DuplicateGroupDialog(QDialog):
    """Modal dialog to mark which duplicate files should be kept."""

    def __init__(self, parent: QWidget, group: DuplicateGroup, protected_paths: set[str]) -> None:
        """Initialize duplicate group selection dialog.

        Args:
            parent: Parent widget.
            group: Duplicate group to display.
            protected_paths: Lower-cased absolute paths currently marked as keep.
        """
        super().__init__(parent)
        self.group = group
        self.selected_paths: set[str] | None = None

        self.setWindowTitle("Kopya grubu")
        self.setModal(True)
        self.resize(960, 440)

        group_paths = {str(item.full_path).lower() for item in group.files}
        active_keep = {item for item in protected_paths if item in group_paths}
        if not active_keep and group.files:
            active_keep = {str(group.files[0].full_path).lower()}

        root = QVBoxLayout()
        header = QLabel(f"Hash: {group.sha256_hash[:16]}...   Toplam dosya: {len(group.files)}")
        header.setStyleSheet("font-weight:600;")
        hint = QLabel("Koru işaretli dosyalar silinmez/karantinaya alınmaz.")
        hint.setStyleSheet("color: #6b7280;")
        root.addWidget(header)
        root.addWidget(hint)

        self.table = QTableWidget(len(group.files), 4)
        self.table.setHorizontalHeaderLabels(["Koru", "Boyut", "Tarih", "Dosya"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        for row, file in enumerate(group.files):
            path_text = str(file.full_path)
            path_key = path_text.lower()

            keep_item = QTableWidgetItem()
            keep_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            keep_item.setCheckState(Qt.CheckState.Checked if path_key in active_keep else Qt.CheckState.Unchecked)
            keep_item.setData(Qt.ItemDataRole.UserRole, path_key)
            self.table.setItem(row, 0, keep_item)

            size_item = QTableWidgetItem(format_size(file.size_bytes))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, QTableWidgetItem(file.last_write_utc.astimezone().strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 3, QTableWidgetItem(path_text))

        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addItem(QSpacerItem(10, 10, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        cancel = QPushButton("Vazgeç")
        save = QPushButton("Seçimi Kaydet")
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        root.addLayout(actions)

        self.setLayout(root)

    @Slot()
    def _save(self) -> None:
        """Store selected keep-path list and close dialog."""
        selected: set[str] = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                key = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(key, str):
                    selected.add(key)

        if not selected:
            QMessageBox.warning(self, TR["err"], "En az 1 dosya korunmalı.")
            return

        self.selected_paths = selected
        self.accept()


class Worker(QObject):
    """Background worker executed inside a dedicated QThread."""

    log = Signal(str)
    progress = Signal(object)  # OperationProgress
    completed = Signal(object)  # RunResult
    cancelled = Signal()
    failed = Signal(str)

    def __init__(
        self,
        engine: ArchiFlowEngine,
        options: RunOptions,
        cancel_event: threading.Event,
        pause_controller: PauseController,
    ) -> None:
        """Initialize worker state.

        Args:
            engine: Pipeline engine instance.
            options: Run options to execute.
            cancel_event: Shared cancellation event.
            pause_controller: Shared pause controller.
        """
        super().__init__()
        self.engine = engine
        self.options = options
        self.cancel_event = cancel_event
        self.pause_controller = pause_controller

    @Slot()
    def run(self) -> None:
        """Run engine and emit completed/cancelled/failed signals."""
        try:
            if self.cancel_event.is_set():
                self.cancelled.emit()
                return
            result = self.engine.run(
                self.options,
                log=lambda message: self.log.emit(str(message)),
                progress=lambda progress: self.progress.emit(progress),
                cancel_event=self.cancel_event,
                pause_controller=self.pause_controller,
            )
            self.completed.emit(result)
        except OperationCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            msg = f"{exc}\n\n{traceback.format_exc()}"
            self.failed.emit(msg)
        finally:
            # Ensure no paused state leaks into next run lifecycle.
            self.pause_controller.resume()
