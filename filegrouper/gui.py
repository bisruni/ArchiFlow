from __future__ import annotations

import os
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread
from PySide6.QtGui import QAction, QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QSpacerItem,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    import qdarktheme  # type: ignore
except ImportError:
    qdarktheme = None

from .errors import OperationCancelledError
from .models import DedupeMode, DuplicateGroup, ExecutionScope, OperationProgress, OrganizationMode, ScanFilterOptions
from .pause_controller import PauseController
from .pipeline import FileGrouperEngine, RunOptions, RunResult
from .utils import format_size


# ----------------------------
# i18n (TR only, clean)
# ----------------------------

TR = {
    "title": "ArchiFlow",
    "subtitle": "Disk düzenleme ve kopya temizleme merkezi",
    "source": "Kaynak klasör",
    "target": "Hedef klasör (organize/karantina)",
    "browse": "Gözat…",
    "scope": "Kapsam",
    "workflow": "İş akışı",
    "flow_all": "Hepsi",
    "flow_all_desc": "Gruplandırma ve kopya temizleme birlikte çalışır.",
    "flow_dedupe": "Kopya Analizi",
    "flow_dedupe_desc": "Sadece kopya analiz/temizleme çalışır.",
    "flow_group": "Gruplandırma",
    "flow_group_desc": "Sadece klasörleme ve düzenleme çalışır.",
    "target_not_needed": "Bu akışta hedef klasör gerekmez.",
    "mode": "Taşıma modu",
    "dedupe": "Kopya modu",
    "dry_run": "Test modu (önerilir)",
    "similar": "Benzer görselleri analiz et (silinmez)",
    "similar_unavailable": "Benzer goruntu analizi icin Pillow gerekli.",
    "filters": "Filtreler…",
    "preview": "Önizleme",
    "apply": "Uygula",
    "pause": "Duraklat",
    "resume": "Devam",
    "cancel": "İptal",
    "undo": "Geri al",
    "export": "Rapor",
    "tab_dupes": "Kopyalar",
    "tab_logs": "Log",
    "ready": "Hazır",
    "running": "Çalışıyor…",
    "paused": "Duraklatıldı",
    "cancelled": "İptal edildi",
    "done": "Tamamlandı",
    "err": "Hata",
    "need_source": "Kaynak klasör seçmeden başlayamazsın.",
    "need_target_undo": "Geri alma için hedef klasör gerekli.",
    "need_preview": "Önce bir önizleme/uygulama çalıştır.",
    "preview_summary": "Önizleme Özeti",
    "sum_total": "Toplam dosya",
    "sum_dupes": "Kopya bulundu",
    "sum_dupe_groups": "Kopya grup",
    "sum_reclaim": "Kazanılabilir alan",
    "sum_quarantine": "Karantinaya gidecek",
    "sum_organize": "Gruplanacak dosya",
    "sum_errors": "Hata sayısı",
    "sum_skipped": "Atlanan dosya",
    "confirm_apply_title": "Uygulama Onayı",
    "confirm_apply_text": "İşlem uygulanacak. Devam etmek istiyor musun?",
    "summary_dialog_title": "Çalışma Özeti",
    "summary_preview_done": "Önizleme tamamlandı.",
    "open_quarantine": "Karantina Klasörünü Aç",
    "quarantine_missing": "Karantina klasörü henüz oluşmadı.",
    "open_file_location_failed": "Dosya konumu açılamadı.",
    "dupe_detail": "Grup Detayı",
}

SCOPE_ITEMS = [
    ("Grupla + Kopya Temizle", ExecutionScope.GROUP_AND_DEDUPE),
    ("Sadece Grupla", ExecutionScope.GROUP_ONLY),
    ("Sadece Kopya Temizle", ExecutionScope.DEDUPE_ONLY),
]
MODE_ITEMS = [
    ("Kopyala", OrganizationMode.COPY),
    ("Taşı", OrganizationMode.MOVE),
]
DEDUPE_ITEMS = [
    ("Karantina", DedupeMode.QUARANTINE),
    ("Kapalı", DedupeMode.OFF),
    ("Sil (tehlikeli)", DedupeMode.DELETE),
]
WORKFLOW_ITEMS = [
    (TR["flow_all"], ExecutionScope.GROUP_AND_DEDUPE, TR["flow_all_desc"]),
    (TR["flow_dedupe"], ExecutionScope.DEDUPE_ONLY, TR["flow_dedupe_desc"]),
    (TR["flow_group"], ExecutionScope.GROUP_ONLY, TR["flow_group_desc"]),
]


# ----------------------------
# Filters dialog
# ----------------------------

@dataclass
class UiFilterDraft:
    include_ext: str = ""
    exclude_ext: str = ""
    min_mb: str = ""
    max_mb: str = ""
    from_date: str = ""  # YYYY-MM-DD
    to_date: str = ""    # YYYY-MM-DD


class FiltersDialog(QDialog):
    def __init__(self, parent: QWidget, draft: UiFilterDraft):
        super().__init__(parent)
        self.setWindowTitle("Filtreler")
        self.setModal(True)
        self.setMinimumWidth(520)

        self.result: UiFilterDraft | None = None

        self.include = QLineEdit(draft.include_ext)
        self.exclude = QLineEdit(draft.exclude_ext)
        self.min_mb = QLineEdit(draft.min_mb)
        self.max_mb = QLineEdit(draft.max_mb)
        self.from_date = QLineEdit(draft.from_date)
        self.to_date = QLineEdit(draft.to_date)

        form = QGridLayout()
        r = 0
        form.addWidget(QLabel("Sadece uzantılar (örn: jpg,png,mp4)"), r, 0); form.addWidget(self.include, r, 1); r += 1
        form.addWidget(QLabel("Hariç uzantılar (örn: tmp,ds_store)"), r, 0); form.addWidget(self.exclude, r, 1); r += 1
        form.addWidget(QLabel("Min boyut (MB)"), r, 0); form.addWidget(self.min_mb, r, 1); r += 1
        form.addWidget(QLabel("Max boyut (MB)"), r, 0); form.addWidget(self.max_mb, r, 1); r += 1
        form.addWidget(QLabel("Başlangıç (YYYY-AA-GG)"), r, 0); form.addWidget(self.from_date, r, 1); r += 1
        form.addWidget(QLabel("Bitiş (YYYY-AA-GG)"), r, 0); form.addWidget(self.to_date, r, 1); r += 1

        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
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
    def _save(self):
        self.result = UiFilterDraft(
            include_ext=self.include.text().strip(),
            exclude_ext=self.exclude.text().strip(),
            min_mb=self.min_mb.text().strip(),
            max_mb=self.max_mb.text().strip(),
            from_date=self.from_date.text().strip(),
            to_date=self.to_date.text().strip(),
        )
        self.accept()


# ----------------------------
# Duplicate group dialog
# ----------------------------

class DuplicateGroupDialog(QDialog):
    def __init__(self, parent: QWidget, group: DuplicateGroup, protected_paths: set[str]):
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
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        for row, file in enumerate(group.files):
            path_text = str(file.full_path)
            path_key = path_text.lower()

            keep_item = QTableWidgetItem()
            keep_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            keep_item.setCheckState(Qt.Checked if path_key in active_keep else Qt.Unchecked)
            keep_item.setData(Qt.UserRole, path_key)
            self.table.setItem(row, 0, keep_item)

            size_item = QTableWidgetItem(format_size(file.size_bytes))
            size_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, QTableWidgetItem(file.last_write_utc.astimezone().strftime("%Y-%m-%d %H:%M")))
            self.table.setItem(row, 3, QTableWidgetItem(path_text))

        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
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
    def _save(self):
        selected: set[str] = set()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            if item.checkState() == Qt.Checked:
                key = item.data(Qt.UserRole)
                if isinstance(key, str):
                    selected.add(key)

        if not selected:
            QMessageBox.warning(self, TR["err"], "En az 1 dosya korunmalı.")
            return

        self.selected_paths = selected
        self.accept()


# ----------------------------
# Worker thread
# ----------------------------

class Worker(QObject):
    log = Signal(str)
    progress = Signal(object)  # OperationProgress
    completed = Signal(object) # RunResult
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, engine: FileGrouperEngine, options: RunOptions, cancel_event, pause_controller: PauseController):
        super().__init__()
        self.engine = engine
        self.options = options
        self.cancel_event = cancel_event
        self.pause_controller = pause_controller

    @Slot()
    def run(self):
        try:
            result = self.engine.run(
                self.options,
                log=lambda m: self.log.emit(str(m)),
                progress=lambda p: self.progress.emit(p),
                cancel_event=self.cancel_event,
                pause_controller=self.pause_controller,
            )
            self.completed.emit(result)
        except OperationCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            msg = f"{exc}\n\n{traceback.format_exc()}"
            self.failed.emit(msg)


# ----------------------------
# Main Window
# ----------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = FileGrouperEngine()
        self.similar_supported = self.engine.detector.is_similar_supported()

        self.setWindowTitle(TR["title"])
        self.setMinimumSize(1100, 720)

        self.filters_draft = UiFilterDraft()

        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.cancel_event = None
        self.pause_controller = PauseController()
        self.paused = False
        self.last_result: RunResult | None = None
        self.preview_duplicate_groups: list[DuplicateGroup] = []
        self.protected_duplicate_paths: set[str] = set()
        self.last_run_scope: ExecutionScope = ExecutionScope.GROUP_AND_DEDUPE
        self.last_run_dedupe_mode: DedupeMode = DedupeMode.QUARANTINE
        self.last_run_apply_changes: bool = False
        self.preview_quarantine_estimate = 0
        self.preview_organize_estimate = 0

        self._build_ui()
        self._set_running(False)
        self._set_status(TR["ready"])

    # ---- UI construction ----

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout()
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        central.setLayout(root)

        # Top bar
        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        self.title_lbl = QLabel(TR["title"])
        self.title_lbl.setStyleSheet("font-weight:700; font-size:18px;")
        self.sub_lbl = QLabel(TR["subtitle"])
        self.sub_lbl.setStyleSheet("color: rgba(127,127,127,1);")
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.sub_lbl)
        title_row.addLayout(title_col)
        title_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.dry_check = QCheckBox(TR["dry_run"])
        self.dry_check.setChecked(True)
        self.similar_check = QCheckBox(TR["similar"])
        if not self.similar_supported:
            self.similar_check.setChecked(False)
            self.similar_check.setEnabled(False)
            self.similar_check.setToolTip(TR["similar_unavailable"])
        title_row.addWidget(self.dry_check)
        title_row.addWidget(self.similar_check)

        root.addLayout(title_row)

        workflow_card = QGroupBox(TR["workflow"])
        workflow_layout = QVBoxLayout()
        workflow_layout.setContentsMargins(10, 8, 10, 8)
        workflow_layout.setSpacing(6)
        workflow_card.setLayout(workflow_layout)

        self.workflow_tabs = QTabWidget()
        for title, _scope, desc in WORKFLOW_ITEMS:
            page = QWidget()
            page_layout = QVBoxLayout()
            page_layout.setContentsMargins(10, 8, 10, 8)
            hint = QLabel(desc)
            hint.setStyleSheet("color: #6b7280;")
            page_layout.addWidget(hint)
            page_layout.addStretch(1)
            page.setLayout(page_layout)
            self.workflow_tabs.addTab(page, title)
        self.workflow_tabs.currentChanged.connect(self._on_workflow_changed)
        workflow_layout.addWidget(self.workflow_tabs)
        root.addWidget(workflow_card)

        # Card: inputs + options
        card = QGroupBox()
        card.setTitle("")
        card_layout = QGridLayout()
        card_layout.setHorizontalSpacing(10)
        card_layout.setVerticalSpacing(10)
        card.setLayout(card_layout)

        self.source_edit = QLineEdit()
        self.target_edit = QLineEdit()

        src_btn = QPushButton(TR["browse"])
        tgt_btn = QPushButton(TR["browse"])
        src_btn.clicked.connect(self._browse_source)
        tgt_btn.clicked.connect(self._browse_target)

        self.source_lbl = QLabel(TR["source"])
        card_layout.addWidget(self.source_lbl, 0, 0)
        card_layout.addWidget(self.source_edit, 0, 1)
        card_layout.addWidget(src_btn, 0, 2)

        self.target_lbl = QLabel(TR["target"])
        self.target_btn = tgt_btn
        card_layout.addWidget(self.target_lbl, 1, 0)
        card_layout.addWidget(self.target_edit, 1, 1)
        card_layout.addWidget(tgt_btn, 1, 2)

        # Options column
        opt_box = QVBoxLayout()
        self.mode_combo = QComboBox()
        for label, _ in MODE_ITEMS:
            self.mode_combo.addItem(label)
        self.dedupe_combo = QComboBox()
        for label, _ in DEDUPE_ITEMS:
            self.dedupe_combo.addItem(label)

        opt_grid = QGridLayout()
        self.mode_lbl = QLabel(TR["mode"])
        self.dedupe_lbl = QLabel(TR["dedupe"])
        opt_grid.addWidget(self.mode_lbl, 0, 0)
        opt_grid.addWidget(self.mode_combo, 0, 1)
        opt_grid.addWidget(self.dedupe_lbl, 1, 0)
        opt_grid.addWidget(self.dedupe_combo, 1, 1)

        opt_box.addLayout(opt_grid)

        self.filters_btn = QPushButton(TR["filters"])
        self.filters_btn.clicked.connect(self._open_filters)
        opt_box.addWidget(self.filters_btn)

        card_layout.addLayout(opt_box, 0, 3, 2, 1)

        root.addWidget(card)

        # Actions
        actions = QHBoxLayout()
        self.preview_btn = QPushButton(TR["preview"])
        self.apply_btn = QPushButton(TR["apply"])
        self.pause_btn = QPushButton(TR["pause"])
        self.cancel_btn = QPushButton(TR["cancel"])

        self.preview_btn.clicked.connect(lambda: self._start_run(False))
        self.apply_btn.clicked.connect(lambda: self._start_run(True))
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.cancel_btn.clicked.connect(self._cancel_run)

        self.preview_btn.setMinimumWidth(140)
        self.apply_btn.setMinimumWidth(140)

        actions.addWidget(self.preview_btn)
        actions.addWidget(self.apply_btn)
        actions.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        actions.addWidget(self.pause_btn)
        actions.addWidget(self.cancel_btn)
        root.addLayout(actions)

        # Status + progress
        stat_row = QHBoxLayout()
        self.status_lbl = QLabel(TR["ready"])
        self.progress_lbl = QLabel("0%")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        stat_row.addWidget(self.status_lbl)
        stat_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        stat_row.addWidget(self.progress_lbl)

        root.addLayout(stat_row)
        root.addWidget(self.progress)

        # Metrics
        metrics = QHBoxLayout()
        self.m_total = QLabel("0")
        self.m_size = QLabel("0 B")
        self.m_dupes = QLabel("0")
        self.m_reclaim = QLabel("0 B")
        self.m_errors = QLabel("0")
        self.m_similar = QLabel("0")

        def metric(title: str, value_lbl: QLabel) -> QWidget:
            w = QWidget()
            v = QVBoxLayout()
            v.setContentsMargins(0, 0, 0, 0)
            t = QLabel(title)
            t.setStyleSheet("color: rgba(127,127,127,1);")
            value_lbl.setStyleSheet("font-weight:700; font-size:14px;")
            v.addWidget(t)
            v.addWidget(value_lbl)
            w.setLayout(v)
            return w

        metrics.addWidget(metric("Toplam", self.m_total))
        metrics.addWidget(metric("Boyut", self.m_size))
        metrics.addWidget(metric("Kopya", self.m_dupes))
        metrics.addWidget(metric("Kazanım", self.m_reclaim))
        metrics.addWidget(metric("Hata", self.m_errors))
        metrics.addWidget(metric("Benzer", self.m_similar))
        root.addLayout(metrics)

        # Preview summary (trust layer)
        preview_box = QGroupBox(TR["preview_summary"])
        preview_layout = QGridLayout()
        preview_layout.setHorizontalSpacing(14)
        preview_layout.setVerticalSpacing(6)
        preview_box.setLayout(preview_layout)
        self.p_total = QLabel("0")
        self.p_dupes = QLabel("0")
        self.p_dupe_groups = QLabel("0")
        self.p_reclaim = QLabel("0 B")
        self.p_quarantine = QLabel("0")
        self.p_organize = QLabel("0")
        self.p_errors = QLabel("0")
        self.p_skipped = QLabel("0")
        preview_layout.addWidget(QLabel(TR["sum_total"]), 0, 0)
        preview_layout.addWidget(self.p_total, 0, 1)
        preview_layout.addWidget(QLabel(TR["sum_dupes"]), 0, 2)
        preview_layout.addWidget(self.p_dupes, 0, 3)
        preview_layout.addWidget(QLabel(TR["sum_dupe_groups"]), 0, 4)
        preview_layout.addWidget(self.p_dupe_groups, 0, 5)
        preview_layout.addWidget(QLabel(TR["sum_reclaim"]), 0, 6)
        preview_layout.addWidget(self.p_reclaim, 0, 7)
        preview_layout.addWidget(QLabel(TR["sum_quarantine"]), 1, 0)
        preview_layout.addWidget(self.p_quarantine, 1, 1)
        preview_layout.addWidget(QLabel(TR["sum_organize"]), 1, 2)
        preview_layout.addWidget(self.p_organize, 1, 3)
        preview_layout.addWidget(QLabel(TR["sum_errors"]), 1, 4)
        preview_layout.addWidget(self.p_errors, 1, 5)
        preview_layout.addWidget(QLabel(TR["sum_skipped"]), 1, 6)
        preview_layout.addWidget(self.p_skipped, 1, 7)
        root.addWidget(preview_box)

        # Tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Duplicates table
        dupes_wrap = QWidget()
        dupes_layout = QVBoxLayout()
        dupes_layout.setContentsMargins(0, 0, 0, 0)
        dupes_wrap.setLayout(dupes_layout)

        dupes_toolbar = QHBoxLayout()
        self.dupe_detail_btn = QPushButton(TR["dupe_detail"])
        self.dupe_detail_btn.clicked.connect(self._open_selected_duplicate_group_dialog)
        dupes_toolbar.addWidget(self.dupe_detail_btn)
        dupes_toolbar.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        dupes_layout.addLayout(dupes_toolbar)

        self.dupes_table = QTableWidget(0, 4)
        self.dupes_table.setHorizontalHeaderLabels(["Hash", "Kaldır", "Boyut", "Koru/Kalacak"])
        self.dupes_table.horizontalHeader().setStretchLastSection(True)
        self.dupes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.dupes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.dupes_table.setAlternatingRowColors(True)
        self.dupes_table.setToolTip("Cift tiklayinca dosya konumu acilir.")
        self.dupes_table.cellDoubleClicked.connect(self._open_duplicate_location_from_table)
        dupes_layout.addWidget(self.dupes_table)
        self.tabs.addTab(dupes_wrap, TR["tab_dupes"])

        # Logs
        logs_wrap = QWidget()
        logs_layout = QVBoxLayout()
        logs_wrap.setLayout(logs_layout)

        toolbar = QHBoxLayout()
        self.clear_logs_btn = QPushButton("Log temizle")
        self.open_quarantine_btn = QPushButton(TR["open_quarantine"])
        self.undo_btn = QPushButton(TR["undo"])
        self.export_btn = QPushButton(TR["export"])
        self.clear_logs_btn.clicked.connect(self._clear_logs)
        self.open_quarantine_btn.clicked.connect(self._open_quarantine_folder)
        self.undo_btn.clicked.connect(self._undo_last)
        self.export_btn.clicked.connect(self._export_report)

        toolbar.addWidget(self.clear_logs_btn)
        toolbar.addWidget(self.open_quarantine_btn)
        toolbar.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        toolbar.addWidget(self.undo_btn)
        toolbar.addWidget(self.export_btn)
        logs_layout.addLayout(toolbar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)
        logs_layout.addWidget(self.log_text)

        self.tabs.addTab(logs_wrap, TR["tab_logs"])

        # Menu (tiny)
        m = self.menuBar().addMenu("Dosya")
        act_quit = QAction("Çıkış", self)
        act_quit.triggered.connect(self.close)
        m.addAction(act_quit)

        self._on_workflow_changed(self.workflow_tabs.currentIndex())

    # ---- actions ----

    def _browse_source(self):
        path = QFileDialog.getExistingDirectory(self, TR["source"])
        if path:
            self.source_edit.setText(path)
            if not self.target_edit.text().strip():
                p = Path(path)
                self.target_edit.setText(str(p.parent / f"{p.name}_Organized"))

    def _browse_target(self):
        path = QFileDialog.getExistingDirectory(self, TR["target"])
        if path:
            self.target_edit.setText(path)

    def _open_filters(self):
        dlg = FiltersDialog(self, self.filters_draft)
        if dlg.exec() == QDialog.Accepted and dlg.result is not None:
            self.filters_draft = dlg.result
            self._log("Filtreler güncellendi.")

    def _open_quarantine_folder(self):
        source_text = self.source_edit.text().strip()
        target_text = self.target_edit.text().strip()
        if self.last_result is not None:
            base = self.last_result.target_path
        else:
            base = Path(target_text) if target_text else (Path(source_text) if source_text else None)
        if base is None:
            QMessageBox.information(self, TR["open_quarantine"], TR["quarantine_missing"])
            return
        folder = base / ".filegrouper_quarantine"
        if not folder.exists():
            QMessageBox.information(self, TR["open_quarantine"], TR["quarantine_missing"])
            return
        self._open_path_in_file_manager(folder)

    def _toggle_pause(self):
        if not self._is_running():
            return
        self.paused = not self.paused
        if self.paused:
            self.pause_controller.pause()
            self._set_status(TR["paused"])
            self.pause_btn.setText(TR["resume"])
        else:
            self.pause_controller.resume()
            self._set_status(TR["running"])
            self.pause_btn.setText(TR["pause"])

    def _cancel_run(self):
        if not self._is_running():
            return
        if self.cancel_event is not None:
            self.cancel_event.set()

    def _open_selected_duplicate_group_dialog(self):
        row = self.dupes_table.currentRow()
        if row < 0:
            return
        self._open_duplicate_group_dialog(row, 0)

    @Slot(int)
    def _on_workflow_changed(self, index: int):
        if index < 0 or index >= len(WORKFLOW_ITEMS):
            return
        scope = WORKFLOW_ITEMS[index][1]
        includes_grouping = scope.includes_grouping
        includes_dedupe = scope.includes_dedupe

        self.mode_lbl.setEnabled(includes_grouping)
        self.mode_combo.setEnabled(includes_grouping and not self._is_running())

        self.dedupe_lbl.setEnabled(includes_dedupe)
        self.dedupe_combo.setEnabled(includes_dedupe and not self._is_running())

        self.target_lbl.setEnabled(includes_grouping)
        self.target_edit.setEnabled(includes_grouping and not self._is_running())
        self.target_btn.setEnabled(includes_grouping and not self._is_running())
        if includes_grouping:
            self.target_edit.setPlaceholderText("")
        else:
            self.target_edit.setPlaceholderText(TR["target_not_needed"])

        if includes_dedupe:
            self.similar_check.setEnabled(self.similar_supported and not self._is_running())
        else:
            self.similar_check.setChecked(False)
            self.similar_check.setEnabled(False)

    def _undo_last(self):
        target_text = self.target_edit.text().strip()
        if not target_text:
            QMessageBox.warning(self, TR["err"], TR["need_target_undo"])
            return
        try:
            summary = self.engine.transaction_service.undo_last_transaction(Path(target_text))
        except Exception as exc:
            QMessageBox.critical(self, TR["err"], str(exc))
            return

        self._set_metrics_from_summary(summary, similar_count=int(self.m_similar.text() or "0"))
        self._set_status("Geri alındı")
        self._log("Undo tamamlandı.")

    def _export_report(self):
        if self.last_result is None:
            QMessageBox.warning(self, TR["err"], TR["need_preview"])
            return
        directory = QFileDialog.getExistingDirectory(self, "Rapor klasörü seç")
        if not directory:
            return
        report = self.engine.build_report(self.last_result)
        json_path, csv_path, pdf_path = self.engine.report_exporter.export(report, Path(directory))
        QMessageBox.information(self, "Rapor", f"{json_path.name}\n{csv_path.name}\n{pdf_path.name}")

    # ---- run pipeline ----

    def _start_run(self, apply_changes: bool):
        if self._is_running():
            return

        source_text = self.source_edit.text().strip()
        target_text = self.target_edit.text().strip()

        if not source_text:
            QMessageBox.warning(self, TR["err"], TR["need_source"])
            return

        source = Path(source_text)
        target = Path(target_text) if target_text else None
        scope = self._scope_enum()

        error = self.engine.validate_paths(source, target, scope)
        if error and apply_changes:
            QMessageBox.critical(self, TR["err"], error)
            return

        if apply_changes and not self._confirm_apply(scope):
            return

        # “Sil” seçildiyse ekstra uyarı (satılacak ürün: kazaya izin yok)
        if self._dedupe_enum() == DedupeMode.DELETE and apply_changes and not self.dry_check.isChecked():
            ok = QMessageBox.question(
                self,
                "Tehlikeli İşlem",
                "Kopya modu 'Sil' ve test modu kapalı.\nBu işlem geri alınamaz.\nEmin misin?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ok != QMessageBox.Yes:
                return

        # reset ui
        self._clear_logs()
        self._clear_dupes_table()
        self.last_result = None
        if not apply_changes:
            self.preview_duplicate_groups = []
            self.protected_duplicate_paths = set()
            self.preview_quarantine_estimate = 0
            self.preview_organize_estimate = 0
        self.progress.setValue(0)
        self.progress_lbl.setText("0%")
        self._set_status(TR["running"])
        self._set_preview_summary(None)

        # thread init
        import threading as _th
        self.cancel_event = _th.Event()
        self.pause_controller = PauseController()
        self.paused = False
        self.pause_btn.setText(TR["pause"])

        options = RunOptions(
            source_path=source,
            target_path=target,
            organization_mode=self._mode_enum(),
            dedupe_mode=self._dedupe_enum(),
            execution_scope=scope,
            dry_run=self.dry_check.isChecked(),
            detect_similar_images=self.similar_check.isChecked(),
            apply_changes=apply_changes,
            filter_options=self._build_filter_options(),
            duplicate_protected_paths=set(self.protected_duplicate_paths),
        )
        self.last_run_scope = scope
        self.last_run_dedupe_mode = self._dedupe_enum()
        self.last_run_apply_changes = apply_changes

        self.thread = QThread()
        self.worker = Worker(self.engine, options, self.cancel_event, self.pause_controller)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_complete)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failed)

        # cleanup
        self.worker.completed.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_finished)

        self._set_running(True)
        self.thread.start()

    @Slot()
    def _thread_finished(self):
        self._set_running(False)
        self.thread = None
        self.worker = None

    # ---- signals from worker ----

    @Slot(object)
    def _on_progress(self, p: OperationProgress):
        if p.total_files > 0:
            percent = min(100, int((p.processed_files / p.total_files) * 100))
            self.progress.setValue(percent)
            self.progress_lbl.setText(f"{percent}%")
        if p.message:
            self._set_status(p.message)

    @Slot(object)
    def _on_complete(self, result: RunResult):
        self.last_result = result
        s = result.summary
        self.preview_duplicate_groups = result.duplicate_groups
        self.protected_duplicate_paths = {
            str(group.files[0].full_path).lower()
            for group in result.duplicate_groups
            if group.files
        }

        self._set_metrics_from_summary(s, similar_count=len(result.similar_image_groups))
        quarantine_est = s.duplicates_quarantined
        organize_est = s.files_copied + s.files_moved
        if not self.last_run_apply_changes:
            if self.last_run_scope.includes_dedupe and self.last_run_dedupe_mode is not DedupeMode.OFF:
                quarantine_est = s.duplicate_files_found
            if self.last_run_scope.includes_grouping:
                organize_est = max(0, s.total_files_scanned - quarantine_est)
            else:
                organize_est = 0
        self.preview_quarantine_estimate = quarantine_est
        self.preview_organize_estimate = organize_est
        self._set_preview_summary(s, quarantine_est, organize_est)

        # fill dupes table (cap for performance)
        visible_limit = 600
        for group_index, group in enumerate(result.duplicate_groups[:visible_limit]):
            self._add_dupe_row(group_index)
        if len(result.duplicate_groups) > visible_limit:
            self._log(f"Not: {len(result.duplicate_groups) - visible_limit} kopya grup performans icin tabloda gosterilmedi.")

        for err in s.errors:
            self._log(f"ERROR: {err}")

        self._set_status(TR["done"])
        if not self.last_run_apply_changes:
            self._show_summary_dialog(
                title=TR["preview_summary"],
                summary=s,
                quarantine_count=self.preview_quarantine_estimate,
                organize_count=self.preview_organize_estimate,
                include_quarantine=True,
            )

    @Slot()
    def _on_cancelled(self):
        self._set_status(TR["cancelled"])
        self._log("İşlem iptal edildi.")

    @Slot(str)
    def _on_failed(self, msg: str):
        self._set_status(TR["err"])
        self._log("ERROR: " + msg)
        QMessageBox.critical(self, TR["err"], "Bir hata oluştu.\nDetay log sekmesinde.")

    # ---- helpers ----

    def _scope_enum(self) -> ExecutionScope:
        index = self.workflow_tabs.currentIndex()
        if index < 0 or index >= len(WORKFLOW_ITEMS):
            return ExecutionScope.GROUP_AND_DEDUPE
        return WORKFLOW_ITEMS[index][1]

    def _mode_enum(self) -> OrganizationMode:
        return dict(MODE_ITEMS)[self.mode_combo.currentText()]

    def _dedupe_enum(self) -> DedupeMode:
        return dict(DEDUPE_ITEMS)[self.dedupe_combo.currentText()]

    def _build_filter_options(self) -> ScanFilterOptions:
        d = self.filters_draft

        def parse_ext(raw: str) -> list[str]:
            parts = [x.strip() for x in raw.replace(";", ",").split(",")]
            return [x for x in parts if x]

        def parse_mb(raw: str) -> int | None:
            t = raw.strip()
            if not t:
                return None
            try:
                return int(float(t) * 1024 * 1024)
            except ValueError:
                return None

        def parse_date(raw: str):
            t = raw.strip()
            if not t:
                return None
            try:
                return datetime.fromisoformat(t).astimezone()
            except ValueError:
                return None

        return ScanFilterOptions(
            include_extensions=parse_ext(d.include_ext),
            exclude_extensions=parse_ext(d.exclude_ext),
            min_size_bytes=parse_mb(d.min_mb),
            max_size_bytes=parse_mb(d.max_mb),
            from_utc=parse_date(d.from_date),
            to_utc=parse_date(d.to_date),
            exclude_hidden=True,
            exclude_system=True,
        )

    def _set_running(self, running: bool):
        self.preview_btn.setEnabled(not running)
        self.apply_btn.setEnabled(not running)
        self.filters_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.cancel_btn.setEnabled(running)
        self.workflow_tabs.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.dedupe_combo.setEnabled(not running)
        self.dry_check.setEnabled(not running)
        self.dupe_detail_btn.setEnabled(not running)
        self.open_quarantine_btn.setEnabled(not running)

        if not running:
            self.paused = False
            self.pause_btn.setText(TR["pause"])
        self._on_workflow_changed(self.workflow_tabs.currentIndex())

    def _is_running(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def _set_status(self, text: str):
        self.status_lbl.setText(text)

    def _log(self, msg: str):
        self.log_text.append(msg)

    def _clear_logs(self):
        self.log_text.clear()

    def _clear_dupes_table(self):
        self.dupes_table.setRowCount(0)

    def _open_duplicate_location_from_table(self, row: int, _column: int):
        first = self.dupes_table.item(row, 0)
        if first is None:
            return
        open_path = first.data(Qt.UserRole + 1)
        if isinstance(open_path, str) and open_path.strip():
            self._open_path_in_file_manager(Path(open_path))
            return
        group_index = first.data(Qt.UserRole)
        if not isinstance(group_index, int):
            return
        if group_index < 0 or group_index >= len(self.preview_duplicate_groups):
            return
        group = self.preview_duplicate_groups[group_index]
        if not group.files:
            return
        self._open_path_in_file_manager(group.files[0].full_path)

    def _open_duplicate_group_dialog(self, row: int, _column: int):
        first = self.dupes_table.item(row, 0)
        if first is None:
            return
        group_index = first.data(Qt.UserRole)
        if not isinstance(group_index, int):
            return
        if group_index < 0 or group_index >= len(self.preview_duplicate_groups):
            return

        group = self.preview_duplicate_groups[group_index]
        dlg = DuplicateGroupDialog(self, group, self.protected_duplicate_paths)
        if dlg.exec() != QDialog.Accepted or dlg.selected_paths is None:
            return

        group_paths = {str(item.full_path).lower() for item in group.files}
        self.protected_duplicate_paths -= group_paths
        self.protected_duplicate_paths |= dlg.selected_paths
        self._refresh_dupe_row(row, group_index)
        self._log(f"Kopya grubu secimi guncellendi: {group.sha256_hash[:12]}..")

    def _refresh_dupe_row(self, row: int, group_index: int):
        if group_index < 0 or group_index >= len(self.preview_duplicate_groups):
            return
        group = self.preview_duplicate_groups[group_index]
        protected_files = [
            item for item in group.files
            if str(item.full_path).lower() in self.protected_duplicate_paths
        ]
        keep_count = len(protected_files)
        if keep_count <= 0 and group.files:
            keep_count = 1
            protected_files = [group.files[0]]
        remove_count = max(0, len(group.files) - keep_count)
        selected_file = protected_files[0] if protected_files else (group.files[0] if group.files else None)
        keep_text = (
            str(selected_file.full_path)
            if keep_count <= 1 and selected_file is not None
            else f"{keep_count} dosya korunuyor"
        )
        values = [group.sha256_hash[:12] + "..", f"x{remove_count}", format_size(group.size_bytes), keep_text]
        for c, val in enumerate(values):
            item = self.dupes_table.item(row, c) or QTableWidgetItem()
            item.setText(val)
            if c == 0:
                item.setData(Qt.UserRole, group_index)
                item.setData(Qt.UserRole + 1, str(selected_file.full_path) if selected_file is not None else "")
            if c in (0, 1, 2):
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignRight if c == 2 else Qt.AlignLeft))
            self.dupes_table.setItem(row, c, item)

    def _add_dupe_row(self, group_index: int):
        if group_index < 0 or group_index >= len(self.preview_duplicate_groups):
            return
        r = self.dupes_table.rowCount()
        self.dupes_table.insertRow(r)
        self._refresh_dupe_row(r, group_index)

    def _set_metrics_from_summary(self, summary, similar_count: int):
        self.m_total.setText(str(summary.total_files_scanned))
        self.m_size.setText(format_size(summary.total_bytes_scanned))
        self.m_dupes.setText(str(summary.duplicate_files_found))
        self.m_reclaim.setText(format_size(summary.duplicate_bytes_reclaimable))
        self.m_errors.setText(str(len(summary.errors)))
        self.m_similar.setText(str(similar_count))

    def _set_preview_summary(self, summary, quarantine_count: int = 0, organize_count: int = 0):
        if summary is None:
            self.p_total.setText("0")
            self.p_dupes.setText("0")
            self.p_dupe_groups.setText("0")
            self.p_reclaim.setText("0 B")
            self.p_quarantine.setText("0")
            self.p_organize.setText("0")
            self.p_errors.setText("0")
            self.p_skipped.setText("0")
            return
        self.p_total.setText(str(summary.total_files_scanned))
        self.p_dupes.setText(str(summary.duplicate_files_found))
        self.p_dupe_groups.setText(str(summary.duplicate_group_count))
        self.p_reclaim.setText(format_size(summary.duplicate_bytes_reclaimable))
        self.p_quarantine.setText(str(quarantine_count))
        self.p_organize.setText(str(organize_count))
        self.p_errors.setText(str(len(summary.errors)))
        self.p_skipped.setText(str(len(summary.skipped_files)))

    def _summary_text(self, summary, *, quarantine_count: int | None, organize_count: int | None) -> str:
        lines = []
        lines.append(f"{TR['sum_total']}: {summary.total_files_scanned}")
        lines.append(f"{TR['sum_dupe_groups']}: {summary.duplicate_group_count}")
        lines.append(f"{TR['sum_dupes']}: {summary.duplicate_files_found}")
        lines.append(f"{TR['sum_reclaim']}: {format_size(summary.duplicate_bytes_reclaimable)}")
        if quarantine_count is not None:
            lines.append(f"{TR['sum_quarantine']}: {quarantine_count}")
        if organize_count is not None:
            lines.append(f"{TR['sum_organize']}: {organize_count}")
        lines.append(f"{TR['sum_errors']}: {len(summary.errors)}")
        lines.append(f"{TR['sum_skipped']}: {len(summary.skipped_files)}")
        return "\n".join(lines)

    def _show_summary_dialog(
        self,
        *,
        title: str,
        summary,
        quarantine_count: int | None,
        organize_count: int | None,
        include_quarantine: bool,
    ) -> None:
        text = self._summary_text(
            summary,
            quarantine_count=(quarantine_count if include_quarantine else None),
            organize_count=organize_count,
        )
        QMessageBox.information(
            self,
            title or TR["summary_dialog_title"],
            f"{TR['summary_preview_done']}\n\n{text}",
        )

    def _confirm_apply(self, scope: ExecutionScope) -> bool:
        lines = [TR["confirm_apply_text"], ""]
        lines.append(f"- Is akis: {scope.value}")
        lines.append(f"- Test modu: {'Acik' if self.dry_check.isChecked() else 'Kapali'}")
        lines.append(f"- Kopya modu: {self.dedupe_combo.currentText()}")
        lines.append(f"- Gruplama modu: {self.mode_combo.currentText()}")
        if self.last_result is not None:
            s = self.last_result.summary
            lines.append("")
            lines.append("Son onizleme ozeti:")
            lines.append(
                self._summary_text(
                    s,
                    quarantine_count=self.preview_quarantine_estimate,
                    organize_count=self.preview_organize_estimate,
                )
            )
        else:
            lines.append("")
            lines.append("Onizleme sonucu bulunamadi.")

        ok = QMessageBox.question(
            self,
            TR["confirm_apply_title"],
            "\n".join(lines),
            QMessageBox.Yes | QMessageBox.No,
        )
        return ok == QMessageBox.Yes

    def _open_path_in_file_manager(self, path: Path):
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", str(path)], check=False)
            elif os.name == "nt":
                subprocess.run(["explorer", f"/select,{path}"], check=False)
            else:
                target = path if path.is_dir() else path.parent
                subprocess.run(["xdg-open", str(target)], check=False)
        except Exception:
            QMessageBox.warning(self, TR["err"], TR["open_file_location_failed"])

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._is_running():
            super().closeEvent(event)
            return

        self._set_status("Kapatiliyor...")
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.pause_controller.resume()

        if self.thread is not None:
            self.thread.wait(3000)
            if self.thread.isRunning():
                QMessageBox.warning(
                    self,
                    TR["err"],
                    "Islem hala devam ediyor. Lutfen once Iptal ile durdurun.",
                )
                event.ignore()
                return

        super().closeEvent(event)


def launch_gui() -> None:
    app = QApplication(sys.argv)

    # Better fonts on macOS/Win
    app.setFont(QFont("SF Pro Text", 11))

    # Theme: try qdarktheme, otherwise use a clean built-in light stylesheet
    themed = False
    if qdarktheme is not None:
        # qdarktheme has had different APIs across versions.
        for fn_name in ("setup_theme", "load_stylesheet"):
            fn = getattr(qdarktheme, fn_name, None)
            if callable(fn):
                try:
                    if fn_name == "setup_theme":
                        fn("light")
                    else:
                        # Some versions expose load_stylesheet() -> str
                        css = fn(theme="light") if "theme" in fn.__code__.co_varnames else fn()
                        if isinstance(css, str) and css.strip():
                            app.setStyleSheet(css)
                    themed = True
                    break
                except Exception:
                    pass

    if not themed:
        # Minimal modern light theme (no external dependency)
        app.setStyleSheet("""
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
        """)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
