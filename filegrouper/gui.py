from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .models import DedupeMode, ExecutionScope, OperationProgress, OrganizationMode, ScanFilterOptions
from .pause_controller import PauseController
from .pipeline import FileGrouperEngine, RunOptions, RunResult
from .scanner import OperationCancelledError
from .utils import format_size


PALETTE = {
    "page": "#f6f7f9",
    "card": "#ffffff",
    "card_alt": "#fafbfc",
    "border": "#e2e7ee",
    "hero": "#ffffff",
    "hero_text": "#111827",
    "hero_sub": "#6b7280",
    "text": "#1f2937",
    "muted": "#6b7280",
    "accent": "#2563eb",
    "accent_dark": "#1d4ed8",
    "positive": "#15803d",
    "warning": "#a16207",
    "danger": "#dc2626",
}

LANG_TEXTS = {
    "Turkce": {
        "title": "FileGrouper",
        "subtitle": "Disk duzenleme ve kopya temizleme merkezi",
        "source": "Kaynak Klasor",
        "target": "Hedef Klasor",
        "browse": "Gozat",
        "scope": "Calisma Kapsami",
        "mode": "Gruplama Modu",
        "dedupe": "Kopya Modu",
        "dry_run": "Test modu (onerilen)",
        "similar": "Benzer gorselleri bul",
        "preview": "Onizleme",
        "apply": "Secili Islemi Uygula",
        "pause": "Duraklat",
        "resume": "Devam Et",
        "cancel": "Iptal",
        "undo": "Son Islemi Geri Al",
        "export": "Rapor Disa Aktar",
        "filters": "Filtreler",
        "include_ext": "Sadece uzantilar",
        "exclude_ext": "Haric uzantilar",
        "min_mb": "Min MB",
        "max_mb": "Max MB",
        "from_date": "Baslangic (YYYY-AA-GG)",
        "to_date": "Bitis (YYYY-AA-GG)",
        "advanced_toggle": "Gelismis secenekleri goster",
        "status_ready": "Hazir",
        "status_running": "Calisiyor...",
        "status_done": "Tamamlandi",
        "status_cancelled": "Iptal edildi",
        "status_paused": "Duraklatildi",
        "status_resumed": "Devam ediyor",
        "progress_title": "Ilerleme",
        "tab_duplicates": "Kopya Gruplari",
        "tab_logs": "Log Akisi",
        "tab_quick": "Hizli Kullanim",
        "quick": "1) Kaynak sec\n2) Kapsam sec\n3) Onizleme\n4) Test modunu kapatip uygula",
        "summary_total": "Toplam Dosya",
        "summary_size": "Toplam Boyut",
        "summary_dupes": "Kopya Dosya",
        "summary_reclaim": "Kazanilabilir",
        "summary_err": "Hata",
        "summary_similar": "Benzer Grup",
        "dup_hash": "Hash",
        "dup_remove": "Silinecek",
        "dup_size": "Boyut",
        "dup_keep": "Kalinacak Dosya",
        "similar_list": "Benzer Goruntuler",
        "clear_logs": "Log Temizle",
        "language": "Dil",
    },
    "English": {
        "title": "FileGrouper",
        "subtitle": "Disk organization and duplicate cleanup center",
        "source": "Source Folder",
        "target": "Target Folder",
        "browse": "Browse",
        "scope": "Execution Scope",
        "mode": "Grouping Mode",
        "dedupe": "Duplicate Mode",
        "dry_run": "Dry run (recommended)",
        "similar": "Find similar images",
        "preview": "Preview",
        "apply": "Apply Selected Operation",
        "pause": "Pause",
        "resume": "Resume",
        "cancel": "Cancel",
        "undo": "Undo Last Operation",
        "export": "Export Report",
        "filters": "Filters",
        "include_ext": "Include extensions",
        "exclude_ext": "Exclude extensions",
        "min_mb": "Min MB",
        "max_mb": "Max MB",
        "from_date": "From (YYYY-MM-DD)",
        "to_date": "To (YYYY-MM-DD)",
        "advanced_toggle": "Show advanced options",
        "status_ready": "Ready",
        "status_running": "Running...",
        "status_done": "Completed",
        "status_cancelled": "Cancelled",
        "status_paused": "Paused",
        "status_resumed": "Running",
        "progress_title": "Progress",
        "tab_duplicates": "Duplicate Groups",
        "tab_logs": "Log Stream",
        "tab_quick": "Quick Start",
        "quick": "1) Select source\n2) Select scope\n3) Preview\n4) Turn off dry run and apply",
        "summary_total": "Total Files",
        "summary_size": "Total Size",
        "summary_dupes": "Duplicate Files",
        "summary_reclaim": "Reclaimable",
        "summary_err": "Errors",
        "summary_similar": "Similar Groups",
        "dup_hash": "Hash",
        "dup_remove": "To Remove",
        "dup_size": "Size",
        "dup_keep": "File To Keep",
        "similar_list": "Similar Images",
        "clear_logs": "Clear Logs",
        "language": "Language",
    },
}


class FileGrouperApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.engine = FileGrouperEngine()
        self.title("FileGrouper")
        self.geometry("1360x860")
        self.minsize(1120, 720)
        self.configure(bg=PALETTE["page"])

        self.language_var = tk.StringVar(value="Turkce")
        self.source_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.scope_var = tk.StringVar(value="Grupla + Kopya Temizle")
        self.mode_var = tk.StringVar(value="Kopyala")
        self.dedupe_var = tk.StringVar(value="Karantina")
        self.dry_run_var = tk.BooleanVar(value=True)
        self.similar_var = tk.BooleanVar(value=False)
        self.show_advanced_var = tk.BooleanVar(value=False)

        self.include_ext_var = tk.StringVar()
        self.exclude_ext_var = tk.StringVar()
        self.min_size_var = tk.StringVar()
        self.max_size_var = tk.StringVar()
        self.from_date_var = tk.StringVar()
        self.to_date_var = tk.StringVar()

        self.status_var = tk.StringVar(value="Hazir")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.summary_vars = {
            "total": tk.StringVar(value="0"),
            "size": tk.StringVar(value="0 B"),
            "dupes": tk.StringVar(value="0"),
            "reclaim": tk.StringVar(value="0 B"),
            "errors": tk.StringVar(value="0"),
            "similar": tk.StringVar(value="0"),
        }

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.pause_controller = PauseController()
        self.paused = False
        self.last_result: RunResult | None = None

        self._configure_style()
        self._build_ui()
        self._apply_language()
        self._set_running(False)
        self.after(120, self._poll_queue)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        base_font = ("Avenir Next", 11)
        style.configure("TFrame", background=PALETTE["page"])
        style.configure("Card.TFrame", background=PALETTE["card"], borderwidth=1, relief="solid", bordercolor=PALETTE["border"])
        style.configure("SoftCard.TFrame", background=PALETTE["card_alt"], borderwidth=1, relief="solid", bordercolor=PALETTE["border"])
        style.configure("TLabel", background=PALETTE["page"], foreground=PALETTE["text"], font=base_font)
        style.configure("Card.TLabel", background=PALETTE["card"], foreground=PALETTE["text"], font=base_font)
        style.configure("Muted.TLabel", background=PALETTE["card"], foreground=PALETTE["muted"], font=("Avenir Next", 10))
        style.configure("MetricName.TLabel", background=PALETTE["card_alt"], foreground=PALETTE["muted"], font=("Avenir Next", 10))
        style.configure("MetricValue.TLabel", background=PALETTE["card_alt"], foreground=PALETTE["text"], font=("Avenir Next Demi Bold", 15))
        style.configure("Heading.TLabel", background=PALETTE["card"], foreground=PALETTE["text"], font=("Avenir Next Demi Bold", 13))

        style.configure("TEntry", fieldbackground="#ffffff", foreground=PALETTE["text"], bordercolor=PALETTE["border"])
        style.configure("TCombobox", fieldbackground="#ffffff", foreground=PALETTE["text"], bordercolor=PALETTE["border"])

        style.configure("Primary.TButton", foreground="#ffffff", background=PALETTE["accent"], bordercolor=PALETTE["accent_dark"], padding=(14, 9))
        style.map("Primary.TButton", background=[("active", "#3b82f6")])

        style.configure("Secondary.TButton", foreground=PALETTE["text"], background="#ffffff", bordercolor=PALETTE["border"], padding=(12, 8))
        style.map("Secondary.TButton", background=[("active", "#f3f4f6")])

        style.configure("Danger.TButton", foreground="#ffffff", background="#d94848", bordercolor="#c03b3b", padding=(12, 8))
        style.map("Danger.TButton", background=[("active", "#ef5e5e")])

        style.configure("TNotebook", background=PALETTE["card"], borderwidth=0)
        style.configure("TNotebook.Tab", font=("Avenir Next Demi Bold", 10), padding=(14, 8), background="#f3f4f6", foreground=PALETTE["muted"])
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", PALETTE["text"])])

        style.configure("TLabelframe", background=PALETTE["card"], bordercolor=PALETTE["border"])
        style.configure("TLabelframe.Label", background=PALETTE["card"], foreground=PALETTE["muted"], font=("Avenir Next Demi Bold", 10))

        style.configure("TProgressbar", troughcolor="#eceff4", background=PALETTE["accent"], bordercolor=PALETTE["border"])

    def _build_ui(self) -> None:
        shell = ttk.Frame(self)
        shell.pack(fill="both", expand=True, padx=14, pady=14)
        shell.rowconfigure(1, weight=1)
        shell.columnconfigure(0, weight=1)

        self._build_header(shell)

        body = ttk.Frame(shell)
        body.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)

        left_panel = ttk.Frame(body, style="Card.TFrame", padding=12)
        left_panel.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        left_panel.configure(width=380)
        left_panel.grid_propagate(False)
        self._build_left_panel(left_panel)

        right_panel = ttk.Frame(body)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.rowconfigure(1, weight=1)
        right_panel.columnconfigure(0, weight=1)

        self._build_metrics(right_panel)
        self._build_tabs(right_panel)

        footer = ttk.Frame(shell, style="Card.TFrame", padding=(10, 9))
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(1, weight=1)

        self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Card.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")

        self.progress_line = ttk.Progressbar(footer, variable=self.progress_var, maximum=100)
        self.progress_line.grid(row=0, column=1, sticky="ew", padx=(10, 0))

    def _build_header(self, parent: ttk.Frame) -> None:
        hero = ttk.Frame(parent, style="Card.TFrame", padding=(14, 12))
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_columnconfigure(0, weight=1)

        title_col = ttk.Frame(hero, style="Card.TFrame")
        title_col.grid(row=0, column=0, sticky="w")

        self.title_label = ttk.Label(title_col, text="FileGrouper", style="Heading.TLabel")
        self.title_label.pack(anchor="w")

        self.subtitle_label = ttk.Label(title_col, text="", style="Muted.TLabel")
        self.subtitle_label.pack(anchor="w", pady=(2, 0))

        right_col = ttk.Frame(hero, style="Card.TFrame")
        right_col.grid(row=0, column=1, sticky="e")

        self.lang_label = ttk.Label(right_col, style="Muted.TLabel")
        self.lang_label.grid(row=0, column=0, sticky="e", padx=(0, 6))

        self.lang_combo = ttk.Combobox(right_col, values=["Turkce", "English"], textvariable=self.language_var, width=10, state="readonly")
        self.lang_combo.grid(row=0, column=1, sticky="e")
        self.lang_combo.bind("<<ComboboxSelected>>", lambda _: self._apply_language())

        self.dry_check = ttk.Checkbutton(right_col, variable=self.dry_run_var)
        self.dry_check.grid(row=1, column=0, columnspan=2, sticky="e", pady=(4, 0))

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        self.source_label = ttk.Label(parent, style="Card.TLabel")
        self.source_label.pack(anchor="w")
        source_row = ttk.Frame(parent, style="Card.TFrame")
        source_row.pack(fill="x", pady=(4, 8))
        ttk.Entry(source_row, textvariable=self.source_var).pack(side="left", fill="x", expand=True)
        self.source_btn = ttk.Button(source_row, style="Secondary.TButton", command=self._browse_source)
        self.source_btn.pack(side="left", padx=(6, 0))

        self.target_label = ttk.Label(parent, style="Card.TLabel")
        self.target_label.pack(anchor="w")
        target_row = ttk.Frame(parent, style="Card.TFrame")
        target_row.pack(fill="x", pady=(4, 8))
        ttk.Entry(target_row, textvariable=self.target_var).pack(side="left", fill="x", expand=True)
        self.target_btn = ttk.Button(target_row, style="Secondary.TButton", command=self._browse_target)
        self.target_btn.pack(side="left", padx=(6, 0))

        self.scope_label = ttk.Label(parent, style="Card.TLabel")
        self.scope_label.pack(anchor="w")
        self.scope_combo = ttk.Combobox(parent, textvariable=self.scope_var, state="readonly")
        self.scope_combo.pack(fill="x", pady=(4, 8))

        self.advanced_toggle = ttk.Checkbutton(parent, variable=self.show_advanced_var, command=self._toggle_advanced)
        self.advanced_toggle.pack(anchor="w", pady=(0, 8))

        self.advanced_section = ttk.Frame(parent, style="Card.TFrame")

        options_row = ttk.Frame(self.advanced_section, style="Card.TFrame")
        options_row.pack(fill="x", pady=(0, 8))
        options_row.columnconfigure(0, weight=1)
        options_row.columnconfigure(1, weight=1)

        self.mode_label = ttk.Label(options_row, style="Card.TLabel")
        self.mode_label.grid(row=0, column=0, sticky="w")
        self.dedupe_label = ttk.Label(options_row, style="Card.TLabel")
        self.dedupe_label.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.mode_combo = ttk.Combobox(options_row, textvariable=self.mode_var, state="readonly")
        self.mode_combo.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.dedupe_combo = ttk.Combobox(options_row, textvariable=self.dedupe_var, state="readonly")
        self.dedupe_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))

        self.similar_check = ttk.Checkbutton(self.advanced_section, variable=self.similar_var)
        self.similar_check.pack(anchor="w", pady=(2, 10))

        self.filters_frame = ttk.LabelFrame(self.advanced_section)
        self.filters_frame.pack(fill="x", pady=(0, 10))

        self.include_label = ttk.Label(self.filters_frame)
        self.include_label.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        ttk.Entry(self.filters_frame, textvariable=self.include_ext_var).grid(row=1, column=0, sticky="ew", padx=8)

        self.exclude_label = ttk.Label(self.filters_frame)
        self.exclude_label.grid(row=2, column=0, sticky="w", padx=8, pady=(8, 2))
        ttk.Entry(self.filters_frame, textvariable=self.exclude_ext_var).grid(row=3, column=0, sticky="ew", padx=8)

        size_row = ttk.Frame(self.filters_frame)
        size_row.grid(row=4, column=0, sticky="ew", padx=8, pady=(8, 2))
        size_row.columnconfigure(1, weight=1)
        size_row.columnconfigure(3, weight=1)

        self.min_label = ttk.Label(size_row)
        self.min_label.grid(row=0, column=0, sticky="w")
        ttk.Entry(size_row, textvariable=self.min_size_var, width=8).grid(row=0, column=1, sticky="ew", padx=(4, 8))

        self.max_label = ttk.Label(size_row)
        self.max_label.grid(row=0, column=2, sticky="w")
        ttk.Entry(size_row, textvariable=self.max_size_var, width=8).grid(row=0, column=3, sticky="ew", padx=(4, 0))

        date_row = ttk.Frame(self.filters_frame)
        date_row.grid(row=5, column=0, sticky="ew", padx=8, pady=(8, 10))
        date_row.columnconfigure(1, weight=1)
        date_row.columnconfigure(3, weight=1)

        self.from_label = ttk.Label(date_row)
        self.from_label.grid(row=0, column=0, sticky="w")
        ttk.Entry(date_row, textvariable=self.from_date_var, width=10).grid(row=0, column=1, sticky="ew", padx=(4, 8))

        self.to_label = ttk.Label(date_row)
        self.to_label.grid(row=0, column=2, sticky="w")
        ttk.Entry(date_row, textvariable=self.to_date_var, width=10).grid(row=0, column=3, sticky="ew", padx=(4, 0))

        self.filters_frame.columnconfigure(0, weight=1)

        self.actions = ttk.Frame(parent, style="Card.TFrame")
        self.actions.pack(fill="x")
        self.actions.columnconfigure(0, weight=1)
        self.actions.columnconfigure(1, weight=1)

        self.preview_btn = ttk.Button(self.actions, style="Primary.TButton", command=lambda: self._start_run(False))
        self.preview_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))

        self.apply_btn = ttk.Button(self.actions, style="Primary.TButton", command=lambda: self._start_run(True))
        self.apply_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))

        self.pause_btn = ttk.Button(self.actions, style="Secondary.TButton", command=self._toggle_pause)
        self.pause_btn.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))

        self.cancel_btn = ttk.Button(self.actions, style="Danger.TButton", command=self._cancel_run)
        self.cancel_btn.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))

        self.undo_btn = ttk.Button(self.actions, style="Secondary.TButton", command=self._undo_last)
        self.undo_btn.grid(row=2, column=0, sticky="ew", padx=(0, 4))

        self.export_btn = ttk.Button(self.actions, style="Secondary.TButton", command=self._export_report)
        self.export_btn.grid(row=2, column=1, sticky="ew", padx=(4, 0))

        self._toggle_advanced()

    def _build_metrics(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.grid(row=0, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)

        top = ttk.Frame(card, style="Card.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self.progress_title = ttk.Label(top, style="Muted.TLabel", text="Progress")
        self.progress_title.grid(row=0, column=0, sticky="w")
        self.progress_label = ttk.Label(top, style="Muted.TLabel", text="0%")
        self.progress_label.grid(row=0, column=1, sticky="e")

        self.progress_card = ttk.Progressbar(card, variable=self.progress_var, maximum=100)
        self.progress_card.grid(row=1, column=0, sticky="ew", pady=(8, 10))

        grid = ttk.Frame(card, style="Card.TFrame")
        grid.grid(row=2, column=0, sticky="ew")
        for col in range(3):
            grid.columnconfigure(col, weight=1)

        self.summary_text_labels: dict[str, ttk.Label] = {}
        keys = ["total", "size", "dupes", "reclaim", "errors", "similar"]
        for idx, key in enumerate(keys):
            row, col = divmod(idx, 3)
            tile = ttk.Frame(grid, style="SoftCard.TFrame", padding=(10, 8))
            tile.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            name = ttk.Label(tile, style="MetricName.TLabel")
            name.pack(anchor="w")
            value = ttk.Label(tile, style="MetricValue.TLabel", textvariable=self.summary_vars[key])
            value.pack(anchor="w", pady=(2, 0))
            self.summary_text_labels[key] = name

    def _build_tabs(self, parent: ttk.Frame) -> None:
        body = ttk.Frame(parent, style="Card.TFrame", padding=8)
        body.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(body)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        dup_tab = ttk.Frame(self.notebook)
        log_tab = ttk.Frame(self.notebook)
        quick_tab = ttk.Frame(self.notebook)

        self.notebook.add(dup_tab, text="")
        self.notebook.add(log_tab, text="")
        self.notebook.add(quick_tab, text="")

        dup_tab.rowconfigure(0, weight=1)
        dup_tab.rowconfigure(2, weight=1)
        dup_tab.columnconfigure(0, weight=1)

        self.dup_tree = ttk.Treeview(dup_tab, columns=("hash", "remove", "size", "keep"), show="headings", height=10)
        self.dup_tree.grid(row=0, column=0, sticky="nsew")

        dup_scroll = ttk.Scrollbar(dup_tab, orient="vertical", command=self.dup_tree.yview)
        dup_scroll.grid(row=0, column=1, sticky="ns")
        self.dup_tree.configure(yscrollcommand=dup_scroll.set)

        self.similar_title = ttk.Label(dup_tab, style="Muted.TLabel")
        self.similar_title.grid(row=1, column=0, sticky="w", pady=(8, 4))

        self.similar_list = tk.Listbox(
            dup_tab,
            bg="#ffffff",
            fg=PALETTE["text"],
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
            font=("Avenir Next", 10),
        )
        self.similar_list.grid(row=2, column=0, sticky="nsew")

        sim_scroll = ttk.Scrollbar(dup_tab, orient="vertical", command=self.similar_list.yview)
        sim_scroll.grid(row=2, column=1, sticky="ns")
        self.similar_list.configure(yscrollcommand=sim_scroll.set)

        log_tab.rowconfigure(1, weight=1)
        log_tab.columnconfigure(0, weight=1)

        log_toolbar = ttk.Frame(log_tab, style="Card.TFrame")
        log_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        log_toolbar.columnconfigure(0, weight=1)

        self.clear_logs_btn = ttk.Button(log_toolbar, style="Secondary.TButton", command=self._clear_logs)
        self.clear_logs_btn.grid(row=0, column=1, sticky="e")

        self.log_text = tk.Text(
            log_tab,
            state="disabled",
            font=("Menlo", 11),
            bg="#ffffff",
            fg="#2d3f56",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=PALETTE["border"],
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        self.log_text.tag_configure("error", foreground="#c24a4a")

        quick_tab.rowconfigure(0, weight=1)
        quick_tab.columnconfigure(0, weight=1)
        self.quick_label = ttk.Label(quick_tab, justify="left", style="Card.TLabel")
        self.quick_label.grid(row=0, column=0, sticky="nw", padx=12, pady=12)

    def _current_text(self) -> dict[str, str]:
        return LANG_TEXTS[self.language_var.get()]

    def _apply_language(self) -> None:
        text = self._current_text()

        self.title(text["title"])
        self.title_label.config(text=text["title"])
        self.subtitle_label.config(text=text["subtitle"])
        self.lang_label.config(text=text["language"])

        self.source_label.config(text=text["source"])
        self.target_label.config(text=text["target"])
        self.source_btn.config(text=text["browse"])
        self.target_btn.config(text=text["browse"])

        self.scope_label.config(text=text["scope"])
        self.advanced_toggle.config(text=text["advanced_toggle"])
        self.mode_label.config(text=text["mode"])
        self.dedupe_label.config(text=text["dedupe"])
        self.dry_check.config(text=text["dry_run"])
        self.similar_check.config(text=text["similar"])

        self.preview_btn.config(text=text["preview"])
        self.apply_btn.config(text=text["apply"])
        self.pause_btn.config(text=text["resume"] if self.paused else text["pause"])
        self.cancel_btn.config(text=text["cancel"])
        self.undo_btn.config(text=text["undo"])
        self.export_btn.config(text=text["export"])

        self.filters_frame.config(text=text["filters"])
        self.include_label.config(text=text["include_ext"])
        self.exclude_label.config(text=text["exclude_ext"])
        self.min_label.config(text=text["min_mb"])
        self.max_label.config(text=text["max_mb"])
        self.from_label.config(text=text["from_date"])
        self.to_label.config(text=text["to_date"])

        self.progress_title.config(text=text["progress_title"])
        self.notebook.tab(0, text=text["tab_duplicates"])
        self.notebook.tab(1, text=text["tab_logs"])
        self.notebook.tab(2, text=text["tab_quick"])
        self.quick_label.config(text=text["quick"])

        self.summary_text_labels["total"].config(text=text["summary_total"])
        self.summary_text_labels["size"].config(text=text["summary_size"])
        self.summary_text_labels["dupes"].config(text=text["summary_dupes"])
        self.summary_text_labels["reclaim"].config(text=text["summary_reclaim"])
        self.summary_text_labels["errors"].config(text=text["summary_err"])
        self.summary_text_labels["similar"].config(text=text["summary_similar"])

        self.similar_title.config(text=text["similar_list"])
        self.clear_logs_btn.config(text=text["clear_logs"])

        self.dup_tree.heading("hash", text=text["dup_hash"])
        self.dup_tree.heading("remove", text=text["dup_remove"])
        self.dup_tree.heading("size", text=text["dup_size"])
        self.dup_tree.heading("keep", text=text["dup_keep"])
        self.dup_tree.column("hash", width=120, stretch=False)
        self.dup_tree.column("remove", width=90, stretch=False, anchor="center")
        self.dup_tree.column("size", width=110, stretch=False, anchor="e")
        self.dup_tree.column("keep", width=520, stretch=True)

        if self.status_var.get() in {"", "Ready", "Hazir"}:
            self.status_var.set(text["status_ready"])

        self.scope_combo["values"] = self._scope_labels()
        if self.scope_var.get() not in self.scope_combo["values"]:
            self.scope_var.set(self._scope_labels()[0])

        self.mode_combo["values"] = self._mode_labels()
        if self.mode_var.get() not in self.mode_combo["values"]:
            self.mode_var.set(self._mode_labels()[0])

        self.dedupe_combo["values"] = self._dedupe_labels()
        if self.dedupe_var.get() not in self.dedupe_combo["values"]:
            self.dedupe_var.set(self._dedupe_labels()[0])

        self._toggle_advanced()

    def _toggle_advanced(self) -> None:
        show = self.show_advanced_var.get()
        if show:
            self.advanced_section.pack(fill="x", pady=(0, 10), before=self.actions)
            self.undo_btn.grid()
            self.export_btn.grid()
        else:
            self.advanced_section.pack_forget()
            self.undo_btn.grid_remove()
            self.export_btn.grid_remove()
            self.similar_var.set(False)

    def _scope_labels(self) -> list[str]:
        if self.language_var.get() == "English":
            return ["Group + Duplicate Cleanup", "Group Only", "Duplicate Cleanup Only"]
        return ["Grupla + Kopya Temizle", "Sadece Grupla", "Sadece Kopya Temizle"]

    def _mode_labels(self) -> list[str]:
        return ["Copy", "Move"] if self.language_var.get() == "English" else ["Kopyala", "Tasi"]

    def _dedupe_labels(self) -> list[str]:
        return ["Quarantine", "Off", "Delete"] if self.language_var.get() == "English" else ["Karantina", "Kapali", "Sil"]

    def _scope_enum(self) -> ExecutionScope:
        current = self.scope_var.get().strip()
        labels = self._scope_labels()
        if current == labels[1]:
            return ExecutionScope.GROUP_ONLY
        if current == labels[2]:
            return ExecutionScope.DEDUPE_ONLY
        return ExecutionScope.GROUP_AND_DEDUPE

    def _mode_enum(self) -> OrganizationMode:
        return OrganizationMode.MOVE if self.mode_var.get() in {"Move", "Tasi"} else OrganizationMode.COPY

    def _dedupe_enum(self) -> DedupeMode:
        value = self.dedupe_var.get()
        if value in {"Off", "Kapali"}:
            return DedupeMode.OFF
        if value in {"Delete", "Sil"}:
            return DedupeMode.DELETE
        return DedupeMode.QUARANTINE

    def _browse_source(self) -> None:
        selected = filedialog.askdirectory()
        if selected:
            self.source_var.set(selected)
            if not self.target_var.get().strip():
                source = Path(selected)
                self.target_var.set(str(source.parent / f"{source.name}_Organized"))

    def _browse_target(self) -> None:
        selected = filedialog.askdirectory()
        if selected:
            self.target_var.set(selected)

    def _build_filter_options(self) -> ScanFilterOptions:
        def parse_ext(raw: str) -> list[str]:
            parts = [item.strip() for item in raw.replace(";", ",").split(",")]
            return [item for item in parts if item]

        def parse_mb(raw: str) -> int | None:
            value = raw.strip()
            if not value:
                return None
            try:
                return int(float(value) * 1024 * 1024)
            except ValueError:
                return None

        def parse_date(raw: str):
            value = raw.strip()
            if not value:
                return None
            try:
                return datetime.fromisoformat(value).astimezone()
            except ValueError:
                return None

        return ScanFilterOptions(
            include_extensions=parse_ext(self.include_ext_var.get()),
            exclude_extensions=parse_ext(self.exclude_ext_var.get()),
            min_size_bytes=parse_mb(self.min_size_var.get()),
            max_size_bytes=parse_mb(self.max_size_var.get()),
            from_utc=parse_date(self.from_date_var.get()),
            to_utc=parse_date(self.to_date_var.get()),
            exclude_hidden=True,
            exclude_system=True,
        )

    def _start_run(self, apply_changes: bool) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        source_text = self.source_var.get().strip()
        target_text = self.target_var.get().strip()

        if not source_text:
            messagebox.showerror("Error", "Source folder required")
            return

        source = Path(source_text)
        target = Path(target_text) if target_text else None
        scope = self._scope_enum()

        error = self.engine.validate_paths(source, target, scope)
        if error and apply_changes:
            messagebox.showerror("Error", error)
            return

        self.cancel_event = threading.Event()
        self.pause_controller = PauseController()
        self.paused = False
        self._set_running(True)

        run_options = RunOptions(
            source_path=source,
            target_path=target,
            organization_mode=self._mode_enum(),
            dedupe_mode=self._dedupe_enum(),
            execution_scope=scope,
            dry_run=self.dry_run_var.get(),
            detect_similar_images=self.similar_var.get(),
            apply_changes=apply_changes,
            filter_options=self._build_filter_options(),
        )

        for item in self.dup_tree.get_children():
            self.dup_tree.delete(item)
        self.similar_list.delete(0, tk.END)
        self._clear_logs()
        self.last_result = None
        self.progress_var.set(0.0)

        self.status_var.set(self._current_text()["status_running"])

        self.worker = threading.Thread(target=self._run_worker, args=(run_options,), daemon=True)
        self.worker.start()

    def _run_worker(self, options: RunOptions) -> None:
        def log(message: str) -> None:
            self.queue.put(("log", message))

        def progress(item: OperationProgress) -> None:
            self.queue.put(("progress", item))

        try:
            result = self.engine.run(
                options,
                log=log,
                progress=progress,
                cancel_event=self.cancel_event,
                pause_controller=self.pause_controller,
            )
            self.queue.put(("complete", result))
        except OperationCancelledError:
            self.queue.put(("cancelled", None))
        except Exception as exc:  # noqa: BLE001
            self.queue.put(("error", str(exc)))

    def _toggle_pause(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            return

        self.paused = not self.paused
        if self.paused:
            self.pause_controller.pause()
            self.status_var.set(self._current_text()["status_paused"])
        else:
            self.pause_controller.resume()
            self.status_var.set(self._current_text()["status_resumed"])

        self.pause_btn.config(text=self._current_text()["resume"] if self.paused else self._current_text()["pause"])

    def _cancel_run(self) -> None:
        if self.worker is None or not self.worker.is_alive():
            return
        self.cancel_event.set()

    def _undo_last(self) -> None:
        target_text = self.target_var.get().strip()
        if not target_text:
            messagebox.showerror("Error", "Target folder required for undo")
            return

        try:
            summary = self.engine.transaction_service.undo_last_transaction(Path(target_text))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Error", str(exc))
            return

        self.summary_vars["total"].set(str(summary.total_files_scanned))
        self.summary_vars["size"].set(format_size(summary.total_bytes_scanned))
        self.summary_vars["dupes"].set(str(summary.duplicate_files_found))
        self.summary_vars["reclaim"].set(format_size(summary.duplicate_bytes_reclaimable))
        self.summary_vars["errors"].set(str(len(summary.errors)))
        self.status_var.set("Undo tamamlandi" if self.language_var.get() == "Turkce" else "Undo completed")

    def _export_report(self) -> None:
        if self.last_result is None:
            messagebox.showerror("Error", "Run preview/apply first")
            return

        directory = filedialog.askdirectory()
        if not directory:
            return

        report = self.engine.build_report(self.last_result)
        json_path, csv_path, pdf_path = self.engine.report_exporter.export(report, Path(directory))
        messagebox.showinfo("Report", f"{json_path.name}\n{csv_path.name}\n{pdf_path.name}")

    def _poll_queue(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._append_log(str(payload))
            elif kind == "progress":
                self._handle_progress(payload)
            elif kind == "complete":
                self._handle_complete(payload)
            elif kind == "cancelled":
                self.status_var.set(self._current_text()["status_cancelled"])
                self._set_running(False)
            elif kind == "error":
                messagebox.showerror("Error", str(payload))
                self._set_running(False)

        self.after(120, self._poll_queue)

    def _handle_progress(self, progress: OperationProgress) -> None:
        if progress.total_files <= 0:
            return

        percent = min(100.0, (progress.processed_files / progress.total_files) * 100.0)
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{percent:0.0f}% - {progress.message}")

    def _handle_complete(self, result: RunResult) -> None:
        self.last_result = result
        summary = result.summary

        self.summary_vars["total"].set(str(summary.total_files_scanned))
        self.summary_vars["size"].set(format_size(summary.total_bytes_scanned))
        self.summary_vars["dupes"].set(str(summary.duplicate_files_found))
        self.summary_vars["reclaim"].set(format_size(summary.duplicate_bytes_reclaimable))
        self.summary_vars["errors"].set(str(len(summary.errors)))
        self.summary_vars["similar"].set(str(len(result.similar_image_groups)))

        for group in result.duplicate_groups[:300]:
            keeper = str(group.files[0].full_path) if group.files else "-"
            self.dup_tree.insert(
                "",
                tk.END,
                values=(
                    f"{group.sha256_hash[:12]}..",
                    f"x{max(0, len(group.files) - 1)}",
                    format_size(group.size_bytes),
                    keeper,
                ),
            )

        self.similar_list.delete(0, tk.END)
        for group in result.similar_image_groups[:200]:
            self.similar_list.insert(tk.END, f"{group.anchor_path.name} (+{len(group.similar_paths)})")

        for error in summary.errors:
            self._append_log(f"ERROR: {error}")

        self.status_var.set(self._current_text()["status_done"])
        self._set_running(False)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        tag = "error" if message.upper().startswith("ERROR") else None
        if tag:
            self.log_text.insert("end", message + "\n", tag)
        else:
            self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_logs(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        control_state = "disabled" if running else "normal"
        self.preview_btn.configure(state=control_state)
        self.apply_btn.configure(state=control_state)

        idle_state = "disabled" if running else "normal"
        self.undo_btn.configure(state=idle_state)
        self.export_btn.configure(state=idle_state)

        active_state = "normal" if running else "disabled"
        self.pause_btn.configure(state=active_state)
        self.cancel_btn.configure(state=active_state)

        if not running:
            self.paused = False
            self.pause_btn.config(text=self._current_text()["pause"])


def launch_gui() -> None:
    app = FileGrouperApp()
    app.mainloop()
