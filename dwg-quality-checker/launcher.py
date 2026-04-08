"""
DWG Quality Checker — Launcher Minimalista v2.1
"""
from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import threading
import traceback
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import yaml

try:
    import tkinterdnd2 as _tkdnd
    _DND_OK = True
except ImportError:
    _DND_OK = False

sys.path.insert(0, str(Path(__file__).parent))

from checker.core import DXFChecker, merge_profiles_into_config
from checker.i18n import _, get_lang, set_lang
from checker.report import (
    generate_batch_dashboard,
    generate_csv_report,
    generate_excel_report,
    generate_html_report,
    generate_pdf_report,
)
from checker.version import APP_VERSION, AUTHOR, COMPANY, EMAIL

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = APP_VERSION

if getattr(sys, 'frozen', False):
    _BASE_DIR = Path(sys.executable).parent   # ao lado do .exe instalado
else:
    _BASE_DIR = Path(__file__).parent          # diretório do projeto

HISTORY_FILE = _BASE_DIR / "history.json"
_LOG_FILE    = _BASE_DIR / "dwg_checker.log"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(_LOG_FILE),
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)


# ── Desktop toast notification ────────────────────────────────────────────────

def _show_toast(title: str, message: str) -> None:
    """Exibe balão de notificação nativo do Windows (sem dependências extras).

    Usa PowerShell + System.Windows.Forms.NotifyIcon. Silencioso em caso de falha.
    """
    try:
        safe_title   = title.replace("'", "").replace('"', "")
        safe_message = message.replace("'", "").replace('"', "")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$n=New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon=[System.Drawing.SystemIcons]::Application;"
            "$n.Visible=$true;"
            f"$n.ShowBalloonTip(4000,'{safe_title}','{safe_message}',"
            "[System.Windows.Forms.ToolTipIcon]::None);"
            "Start-Sleep -Milliseconds 4500;$n.Visible=$false"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", script],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except Exception:
        pass


# ── Default discipline profiles ───────────────────────────────────────────────

def _build_default_profiles() -> dict:
    """Retorna os perfis de disciplina padrão (nomes traduzidos pelo _())."""
    return {
        _("profile_arch"): {
            "layers": {
                "required":          ["TEXTO", "COTA", "PAREDE", "JANELA", "PORTA", "EIXO"],
                "naming_convention": "^[A-Z]{2,8}(-[A-Z0-9_-]+)?$",
            },
            "text":    {"min_height": 1.5, "max_height": 10.0},
            "drawing": {
                "check_entities_on_layer_0": True,
                "check_unused_blocks":       True,
                "check_empty_layers":        True,
                "check_frozen_layers":       True,
                "check_off_layers":          False,
                "check_color_bylayer":       True,
                "check_linetype_bylayer":    True,
                "check_duplicates":          True,
                "check_xrefs":               True,
            },
        },
        _("profile_topo"): {
            "layers": {
                "required":          ["CURVA_MESTRE", "CURVA_SECUND", "PONTO_COTADO", "LIMITE"],
                "naming_convention": "",
            },
            "text":    {"min_height": 0.5, "max_height": 20.0},
            "drawing": {
                "check_entities_on_layer_0": True,
                "check_unused_blocks":       False,
                "check_empty_layers":        False,
                "check_frozen_layers":       True,
                "check_off_layers":          False,
                "check_color_bylayer":       False,
                "check_linetype_bylayer":    False,
                "check_duplicates":          False,
                "check_xrefs":               False,
            },
        },
        _("profile_struct"): {
            "layers": {
                "required":          ["VIGA", "PILAR", "LAJE", "FUNDACAO", "EIXO", "COTA"],
                "naming_convention": "^[A-Z]{2,6}(-[A-Z0-9_-]+)?$",
            },
            "text":    {"min_height": 0.1, "max_height": 5.0},
            "drawing": {
                "check_entities_on_layer_0": True,
                "check_unused_blocks":       True,
                "check_empty_layers":        True,
                "check_frozen_layers":       True,
                "check_off_layers":          True,
                "check_color_bylayer":       True,
                "check_linetype_bylayer":    True,
                "check_duplicates":          True,
                "check_xrefs":               True,
            },
        },
        _("profile_mep"): {
            "layers": {
                "required":          ["HIDRAULICA", "ELETRICA", "AR_COND", "TEXTO", "COTA"],
                "naming_convention": "",
            },
            "text":    {"min_height": 1.5, "max_height": 10.0},
            "drawing": {
                "check_entities_on_layer_0": True,
                "check_unused_blocks":       True,
                "check_empty_layers":        False,
                "check_frozen_layers":       True,
                "check_off_layers":          False,
                "check_color_bylayer":       False,
                "check_linetype_bylayer":    False,
                "check_duplicates":          True,
                "check_xrefs":               True,
            },
        },
    }

# ── Crash handler ─────────────────────────────────────────────────────────────
def _crash_handler(exc_type, exc_value, exc_tb) -> None:
    """Captura exceções não tratadas, registra no log e exibe diálogo."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logging.critical("CRASH:\n%s", msg)
    try:
        messagebox.showerror(
            "Erro Inesperado",
            f"O programa encontrou um erro não esperado.\n\n"
            f"Log salvo em:\n{_LOG_FILE}\n\n"
            f"{exc_type.__name__}: {exc_value}",
        )
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _crash_handler

C = {
    "bg":      "#0f1117", "surface":  "#1a1d27", "surface2": "#21263a",
    "border":  "#2e3347", "accent":   "#3b82f6", "error":    "#ef4444",
    "warning": "#f59e0b", "info":     "#3b82f6", "success":  "#22c55e",
    "text":    "#e2e8f0", "muted":    "#8892a4",
    "err_bg":  "#3d1515", "warn_bg":  "#3d2e0a", "info_bg":  "#0f2444",
}


# ── Treeview style ────────────────────────────────────────────────────────────

def _apply_style() -> None:
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("DWG.Treeview",
                 background=C["surface"], foreground=C["text"],
                 fieldbackground=C["surface"], rowheight=26,
                 borderwidth=0, relief="flat", font=("Segoe UI", 10))
    s.configure("DWG.Treeview.Heading",
                 background=C["surface2"], foreground=C["muted"],
                 borderwidth=0, relief="flat", font=("Segoe UI", 9, "bold"))
    s.map("DWG.Treeview",
          background=[("selected", "#2e3347")],
          foreground=[("selected", C["text"])])
    s.layout("DWG.Treeview", [("DWG.Treeview.treearea", {"sticky": "nsew"})])


# ── History helpers ───────────────────────────────────────────────────────────

def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_history(entries: list) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logging.warning("Não foi possível salvar o histórico: %s", exc)


def _add_to_history(result: dict, html: str | None) -> None:
    entries = _load_history()
    entries.insert(0, {
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "file":      result["file"],
        "file_path": result["file_path"],
        "passed":    result["passed"],
        "errors":    result["errors"],
        "warnings":  result["warnings"],
        "infos":     result["infos"],
        "total":     result["total_issues"],
        "html_path": html,
    })
    _save_history(entries[:40])


# ── History popup window ──────────────────────────────────────────────────────

class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title(_('history_title'))
        self.geometry("760x420")
        self.configure(fg_color=C["bg"])
        self.resizable(True, True)
        self._html_map: dict[str, str | None] = {}
        self._build()
        self.lift()
        self.focus()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        tb = ctk.CTkFrame(self, fg_color="transparent")
        tb.grid(row=0, column=0, padx=14, pady=(12, 6), sticky="ew")
        tb.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(tb, text=_('history_header'),
                     font=ctk.CTkFont(size=13, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(tb, text=_('history_hint'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 0))

        ctk.CTkButton(tb, text=_('btn_open_report'), width=115, height=26,
                      corner_radius=8, fg_color=C["accent"], hover_color="#2f6cd1",
                      font=ctk.CTkFont(size=11, weight="bold"), command=self._open,
        ).grid(row=0, column=1, padx=(0, 8), sticky="e")
        ctk.CTkButton(tb, text=f"📈  {_('chart_title')}", width=120, height=26,
                      corner_radius=8, fg_color=C["surface2"], hover_color=C["border"],
                      font=ctk.CTkFont(size=11), command=self._show_trend,
        ).grid(row=0, column=2, padx=(0, 8), sticky="e")
        ctk.CTkButton(tb, text=f"🗑️  {_('btn_clear')}", width=90, height=26, corner_radius=8,
                      fg_color=C["surface2"], hover_color=C["border"],
                      font=ctk.CTkFont(size=11), command=self._clear
        ).grid(row=0, column=3, sticky="e")

        tc = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        tc.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        tc.grid_columnconfigure(0, weight=1)
        tc.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tc,
            columns=("ts", "file", "status", "errors", "warnings", "infos"),
            show="headings", style="DWG.Treeview", selectmode="browse",
        )
        for col, title, w in [
            ("ts",       _('col_datetime'),  145), ("file",     _('col_file'),  255),
            ("status",   _('col_status'),      82), ("errors",   _('col_errors'),     58),
            ("warnings", _('col_warnings'),      60), ("infos",    _('col_infos'),     52),
        ]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=w, minwidth=50,
                             anchor="w" if col in ("ts", "file") else "center")
        self.tree.tag_configure("pass", foreground=C["success"])
        self.tree.tag_configure("fail", foreground=C["error"])
        self.tree.tag_configure("alt",  background="#1e2235")
        self.tree.bind("<Double-1>", lambda _: self._open())

        vsb = ctk.CTkScrollbar(tc, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        vsb.grid(row=0, column=1, sticky="ns", pady=8)

        ctk.CTkLabel(self, text=_('history_dblclick'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=2, column=0, pady=(0, 8))

        self._refresh()

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._html_map.clear()
        hist = _load_history()
        if not hist:
            self.tree.insert("", "end", values=("—", "—", _('history_empty'), "—", "—", "—"))
            return
        for idx, e in enumerate(hist):
            tag  = "pass" if e["passed"] else "fail"
            tags = (tag, "alt") if idx % 2 else (tag,)
            iid  = str(idx)
            self.tree.insert("", "end", iid=iid, values=(
                e["timestamp"], e["file"],
                _('watch_passed') if e["passed"] else _('watch_failed'),
                e["errors"], e["warnings"], e["infos"],
            ), tags=tags)
            self._html_map[iid] = e.get("html_path")

    def _open(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        html = self._html_map.get(sel[0])
        if html and Path(html).exists():
            webbrowser.open(f"file:///{Path(html).resolve()}")
        else:
            messagebox.showinfo(_('common_not_found_title'), _('common_report_not_found'), parent=self)

    def _show_trend(self) -> None:
        """Abre uma janela com gráfico de tendência de erros ao longo do tempo."""
        history = _load_history()
        if len(history) < 2:
            messagebox.showinfo(_("chart_title"), _("chart_no_data"), parent=self)
            return

        data = list(reversed(history[-20:]))  # mais antigo → mais recente

        win = ctk.CTkToplevel(self)
        win.title(_("chart_title"))
        win.geometry("560x340")
        win.resizable(False, False)
        win.configure(fg_color=C["bg"])
        win.grab_set()
        win.lift()

        # ── Canvas ───────────────────────────────────────────────────────────
        W, H   = 540, 310
        ML, MR, MT, MB = 50, 20, 30, 55   # margens

        canvas = tk.Canvas(win, width=W, height=H, bg=C["bg"],
                           highlightthickness=0, relief="flat")
        canvas.pack(padx=10, pady=8)

        # Escala
        max_err = max(e["errors"] for e in data)
        y_max   = max(max_err + 1, 4)
        n       = len(data)
        plot_w  = W - ML - MR
        plot_h  = H - MT - MB

        def _px(idx: int) -> float:
            return ML + idx * plot_w / (n - 1) if n > 1 else ML + plot_w / 2

        def _py(val: float) -> float:
            return MT + plot_h - (val / y_max) * plot_h

        # Fundo da área de plot
        canvas.create_rectangle(ML, MT, ML + plot_w, MT + plot_h,
                                 fill=C["surface"], outline=C["border"])

        # Grid horizontal
        for tick in range(0, y_max + 1):
            y = _py(tick)
            canvas.create_line(ML, y, ML + plot_w, y, fill=C["border"], dash=(3, 4))
            canvas.create_text(ML - 6, y, text=str(tick),
                               anchor="e", fill=C["muted"], font=("Segoe UI", 8))

        # Linha de tendência
        pts = [(_px(i), _py(e["errors"])) for i, e in enumerate(data)]
        if len(pts) >= 2:
            flat = [v for p in pts for v in p]
            canvas.create_line(*flat, fill=C["accent"], width=2, smooth=True)

        # Pontos e labels X
        for i, (e, (px, py)) in enumerate(zip(data, pts)):
            color = C["success"] if e["passed"] else C["error"]
            r = 5
            canvas.create_oval(px - r, py - r, px + r, py + r,
                                fill=color, outline="", tags="dot")
            # Label X (data abreviada, a cada 2 pontos)
            if i % max(1, n // 8) == 0 or i == n - 1:
                label = e["timestamp"][:10] if len(e.get("timestamp", "")) >= 10 else e.get("timestamp", "")
                canvas.create_text(px, MT + plot_h + 8, text=label,
                                   angle=40, anchor="nw",
                                   fill=C["muted"], font=("Segoe UI", 7))

        # Título
        canvas.create_text(ML, MT - 14, text=_("chart_title"),
                            anchor="w", fill=C["text"],
                            font=("Segoe UI", 10, "bold"))

        # Legenda
        canvas.create_oval(ML, H - 14, ML + 8, H - 6,  fill=C["success"], outline="")
        canvas.create_text(ML + 12, H - 10, text=_("result_passed"),
                           anchor="w", fill=C["muted"], font=("Segoe UI", 8))
        canvas.create_oval(ML + 90, H - 14, ML + 98, H - 6, fill=C["error"], outline="")
        canvas.create_text(ML + 102, H - 10, text=_("result_failed"),
                           anchor="w", fill=C["muted"], font=("Segoe UI", 8))

    def _clear(self) -> None:
        if messagebox.askyesno(_('history_clear_title'), _('history_clear_msg'), parent=self):
            _save_history([])
            self._refresh()


# ── Batch Verification Window ─────────────────────────────────────────────────

class BatchWindow(ctk.CTkToplevel):
    """Verifica todos os arquivos DXF de uma pasta em lote."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title(_('batch_title'))
        self.geometry("760x540")
        self.configure(fg_color=C["bg"])
        self.resizable(True, True)
        self._files: list[str] = []
        self._html_map: dict[str, str | None] = {}
        self._batch_results: list = []
        self._running = False
        self._stop_flag = False
        _apply_style()
        self._build()
        self.lift()
        self.focus()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Folder picker row ─────────────────────────────────────────────────
        fc = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        fc.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")
        fc.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(fc, text=_('batch_folder_label'),
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=0, padx=(14, 8), pady=10, sticky="w")

        self._folder_var = ctk.StringVar()
        ctk.CTkEntry(fc, textvariable=self._folder_var,
                     placeholder_text=_('batch_placeholder'),
                     height=30, corner_radius=8,
                     fg_color=C["surface2"], border_color=C["border"],
                     font=ctk.CTkFont(size=11)
        ).grid(row=0, column=1, padx=(0, 8), pady=10, sticky="ew")

        self._browse_btn = ctk.CTkButton(fc, text=_('btn_open'), width=82, height=30, corner_radius=8,
                         command=self._browse_folder)
        self._browse_btn.grid(row=0, column=2, padx=(0, 12), pady=10)

        ctk.CTkLabel(fc, text=_('batch_flow_hint'),
                 font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=1, column=0, columnspan=3, padx=(14, 12), pady=(0, 8), sticky="w")

        # ── Action row ────────────────────────────────────────────────────────
        ar = ctk.CTkFrame(self, fg_color="transparent")
        ar.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")
        ar.grid_columnconfigure(2, weight=1)

        self._start_btn = ctk.CTkButton(
            ar, text=_('batch_btn_start'), width=130, height=30, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._start,
        )
        self._start_btn.grid(row=0, column=0, padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            ar, text=_('batch_btn_stop'), width=80, height=30, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), state="disabled", command=self._stop_batch,
        )
        self._stop_btn.grid(row=0, column=1, padx=(0, 12))

        self._clear_btn = ctk.CTkButton(
            ar, text=_('batch_btn_clear'), width=78, height=30, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), command=self._clear_batch,
        )
        self._clear_btn.grid(row=0, column=2, padx=(0, 8))

        self._batch_lbl = ctk.CTkLabel(
            ar, text=_('batch_start_hint'),
            font=ctk.CTkFont(size=11), text_color=C["muted"],
        )
        self._batch_lbl.grid(row=0, column=3, sticky="w")

        self._out_btn = ctk.CTkButton(
            ar, text=_('btn_open_folder'), width=88, height=30, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), command=self._open_folder_in_explorer,
        )
        self._out_btn.grid(row=0, column=4, padx=(8, 0))

        self._dashboard_btn = ctk.CTkButton(
            ar, text=_('btn_dashboard'), width=115, height=30, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), state="disabled",
            command=self._open_dashboard,
        )
        self._dashboard_btn.grid(row=0, column=5, padx=(8, 0))

        # ── Results table ─────────────────────────────────────────────────────
        tc = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        tc.grid(row=2, column=0, padx=12, pady=(0, 6), sticky="nsew")
        tc.grid_columnconfigure(0, weight=1)
        tc.grid_rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            tc,
            columns=("file", "status", "errors", "warnings", "infos"),
            show="headings", style="DWG.Treeview", selectmode="browse",
        )
        for col, title, w, anchor in [
            ("file",     _('col_file'),  310, "w"),
            ("status",   _('col_status'),    90, "center"),
            ("errors",   _('col_errors'),     60, "center"),
            ("warnings", _('col_warnings'),    60, "center"),
            ("infos",    _('col_infos'),     55, "center"),
        ]:
            self._tree.heading(col, text=title)
            self._tree.column(col, width=w, minwidth=40, anchor=anchor)

        self._tree.tag_configure("pass",    foreground=C["success"])
        self._tree.tag_configure("fail",    foreground=C["error"])
        self._tree.tag_configure("running", foreground=C["warning"])
        self._tree.tag_configure("err",     foreground=C["warning"])
        self._tree.tag_configure("alt",     background="#1e2235")
        self._tree.bind("<Double-1>", lambda _: self._open_report())

        vsb = ctk.CTkScrollbar(tc, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        vsb.grid(row=0, column=1, sticky="ns", pady=8)

        ctk.CTkLabel(self, text=_('batch_dblclick'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=3, column=0, pady=(0, 2))

        # ── Progress bar footer ───────────────────────────────────────────────
        pf = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=28)
        pf.grid(row=4, column=0, sticky="ew")
        pf.grid_propagate(False)
        pf.grid_columnconfigure(1, weight=1)

        self._batch_prog = ctk.CTkProgressBar(pf, width=200, height=5)
        self._batch_prog.grid(row=0, column=0, padx=(12, 8), pady=10)
        self._batch_prog.set(0)

        self._prog_lbl = ctk.CTkLabel(pf, text="",
                                       font=ctk.CTkFont(size=10), text_color=C["muted"])
        self._prog_lbl.grid(row=0, column=1, sticky="w")

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _browse_folder(self) -> None:
        d = filedialog.askdirectory(title=_('batch_select_folder'))
        if d:
            self._folder_var.set(d)
            self._scan_folder(d)

    def _scan_folder(self, folder: str) -> None:
        files = sorted(Path(folder).rglob("*.dxf"))
        self._files = [str(f) for f in files]
        self._html_map.clear()
        self._tree.delete(*self._tree.get_children())
        for idx, f in enumerate(self._files):
            tags = ("alt",) if idx % 2 else ()
            self._tree.insert("", "end", iid=str(idx),
                               values=(Path(f).name, _('batch_waiting'), "—", "—", "—"),
                               tags=tags)
        n = len(self._files)
        self._batch_lbl.configure(text=_('batch_found', n=n))

    def _start(self) -> None:
        if not self._files:
            folder = self._folder_var.get().strip()
            if folder and Path(folder).exists():
                self._scan_folder(folder)
            if not self._files:
                messagebox.showwarning(_('batch_no_files_title'),
                                       _('batch_no_files_msg'), parent=self)
                return
        self._running    = True
        self._stop_flag  = False
        self._batch_prog.set(0)
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._browse_btn.configure(state="disabled")
        self._clear_btn.configure(state="disabled")
        threading.Thread(target=self._batch_worker, daemon=True).start()

    def _stop_batch(self) -> None:
        self._stop_flag = True
        self._batch_lbl.configure(text=_('batch_stopping'))

    def _batch_worker(self) -> None:
        total = len(self._files)
        for idx, fp in enumerate(self._files):
            if self._stop_flag:
                break
            self.after(0, self._set_running, str(idx))
            try:
                result  = DXFChecker().check(fp)
                out_dir = str(Path(fp).parent)
                base    = str(Path(out_dir) / (Path(fp).stem + "_report"))
                html    = generate_html_report(result, base + ".html")
                _add_to_history(result, html)
                self.after(0, self._set_done, str(idx), result, html)
            except Exception as exc:
                tb = traceback.format_exc()
                logging.error("Lote: erro ao processar '%s':\n%s", fp, tb)
                self.after(0, self._set_err, str(idx), str(exc))
            self.after(0, self._update_progress, idx + 1, total)
        self.after(0, self._batch_finished)

    def _set_running(self, iid: str) -> None:
        base_tags = ("alt",) if int(iid) % 2 else ()
        self._tree.item(iid, tags=("running",) + base_tags)
        vals = list(self._tree.item(iid, "values"))
        vals[1] = _('batch_running')
        self._tree.item(iid, values=vals)

    def _set_done(self, iid: str, result: dict, html: str | None) -> None:
        tag  = "pass" if result["passed"] else "fail"
        base = ("alt",) if int(iid) % 2 else ()
        self._html_map[iid] = html
        self._batch_results.append(result)
        self._tree.item(iid, tags=(tag,) + base, values=(
            Path(result["file_path"]).name,
            _('batch_passed') if result["passed"] else _('batch_failed'),
            result["errors"], result["warnings"], result["infos"],
        ))

    def _set_err(self, iid: str, msg: str) -> None:
        base = ("alt",) if int(iid) % 2 else ()
        self._tree.item(iid, tags=("err",) + base)
        vals = list(self._tree.item(iid, "values"))
        vals[1] = _('batch_error')
        self._tree.item(iid, values=vals)

    def _update_progress(self, done: int, total: int) -> None:
        self._batch_prog.set(done / total)
        self._prog_lbl.configure(text=_('batch_progress', done=done, total=total))
        self._batch_lbl.configure(text=_('batch_processing_hint', done=done, total=total))

    def _batch_finished(self) -> None:
        self._running = False
        passed = sum(1 for v in self._html_map.values() if v)
        total  = len(self._files)
        if self._stop_flag:
            self._batch_lbl.configure(text=_('batch_stopped', n=passed))
        else:
            self._batch_lbl.configure(text=_('batch_finished', ok=passed, total=total))
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._browse_btn.configure(state="normal")
        self._clear_btn.configure(state="normal")
        if self._batch_results:
            self._dashboard_btn.configure(state="normal")

    def _open_folder_in_explorer(self) -> None:
        folder = self._folder_var.get().strip()
        if folder and Path(folder).exists():
            os.startfile(str(Path(folder).resolve()))

    def _clear_batch(self) -> None:
        if self._running:
            return
        self._tree.delete(*self._tree.get_children())
        self._files = []
        self._html_map.clear()
        self._batch_results = []
        self._batch_prog.set(0)
        self._prog_lbl.configure(text="")
        self._dashboard_btn.configure(state="disabled")
        self._batch_lbl.configure(text=_('batch_start_hint'))

    def _open_dashboard(self) -> None:
        results = [r for r in self._batch_results if r]
        if not results:
            return
        folder = self._folder_var.get().strip()
        out_dir = Path(folder) if folder and Path(folder).exists() else Path(results[0]["file_path"]).parent
        out = str(out_dir / "batch_dashboard.html")
        try:
            path = generate_batch_dashboard(results, out)
            webbrowser.open(f"file:///{Path(path).resolve()}")
        except Exception as exc:
            logging.error("Dashboard: %s", exc)
            messagebox.showerror(_('main_error_title'), _('dashboard_error_msg', err=str(exc)), parent=self)

    def _open_report(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        html = self._html_map.get(sel[0])
        if html and Path(html).exists():
            webbrowser.open(f"file:///{Path(html).resolve()}")
        else:
            messagebox.showinfo(_('common_not_found_title'), _('common_report_not_found'), parent=self)


# ── Config Editor Window ──────────────────────────────────────────────────────

class ConfigEditorWindow(ctk.CTkToplevel):
    """Editor visual para config.yaml — sem precisar editar o arquivo manualmente."""

    _CONFIG_FILE   = _BASE_DIR / "config.yaml"
    _PROFILES_FILE = _BASE_DIR / "config_profiles.json"

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title(f"⚙️  {_('config_title')}")
        self.geometry("600x680")
        self.minsize(560, 620)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self._cfg = self._load()
        self._profiles: dict = self._load_profiles()
        self._build()
        self.lift()
        self.focus()

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        try:
            with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as exc:
            logging.warning("ConfigEditor: não carregou config.yaml: %s", exc)
            return {}

    def _collect(self) -> None:
        """Lê widgets e atualiza self._cfg."""
        self._cfg.setdefault("layers", {})
        self._cfg["layers"]["required"] = self._req_layers[:]
        self._cfg["layers"]["naming_convention"] = self._naming_var.get().strip()

        self._cfg.setdefault("text", {})
        for key, attr in (("min_height", "_min_h_var"), ("max_height", "_max_h_var")):
            try:
                self._cfg["text"][key] = float(getattr(self, attr).get().replace(",", "."))
            except ValueError:
                pass

        self._cfg.setdefault("drawing", {})
        for key, var in self._drawing_vars.items():
            self._cfg["drawing"][key] = bool(var.get())
        # Extra rules toggles
        for key, var in getattr(self, "_extra_rule_vars", {}).items():
            self._cfg["drawing"][key] = bool(var.get())
        # Severity overrides
        self._cfg.setdefault("rules", {})
        overrides = {}
        for rule_id, svar in getattr(self, "_sev_vars", {}).items():
            val = svar.get()
            if val and val != _('sev_inherit'):
                overrides[rule_id] = val
        self._cfg["rules"]["severity_overrides"] = overrides

    def _save(self) -> None:
        try:
            self._collect()
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.dump(self._cfg, f, allow_unicode=True,
                          default_flow_style=False, sort_keys=False)
            messagebox.showinfo(_('config_title'), _('config_saved'), parent=self)
            self.destroy()
        except Exception as exc:
            logging.error("ConfigEditor: erro ao salvar: %s", exc)
            messagebox.showerror(_('main_error_title'), _('config_save_error', error=str(exc)), parent=self)

    # ── Perfis de configuração ──────────────────────────────────────────────────

    def _load_profiles(self) -> dict:
        try:
            if self._PROFILES_FILE.exists():
                import json as _json
                with open(self._PROFILES_FILE, "r", encoding="utf-8") as f:
                    data = _json.load(f) or {}
                if data:
                    return data
        except Exception as exc:
            logging.warning("Perfis: falha ao carregar: %s", exc)
        # Primeira execução — semente com perfis de disciplina padrão
        defaults = _build_default_profiles()
        try:
            import json as _json
            with open(self._PROFILES_FILE, "w", encoding="utf-8") as f:
                _json.dump(defaults, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logging.warning("Perfis: falha ao gravar padrões: %s", exc)
        return defaults

    def _persist_profiles(self) -> None:
        try:
            import json as _json
            with open(self._PROFILES_FILE, "w", encoding="utf-8") as f:
                _json.dump(self._profiles, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logging.warning("Perfis: falha ao salvar: %s", exc)

    def _save_profile(self) -> None:
        """Salva a configuração atual como um novo perfil."""
        win = ctk.CTkToplevel(self)
        win.title(_('config_profile_save'))
        win.geometry("340x150")
        win.resizable(False, False)
        win.configure(fg_color=C["bg"])
        win.grab_set()
        ctk.CTkLabel(win, text=_('config_profile_name_label'),
                     font=ctk.CTkFont(size=11), text_color=C["text"]
        ).pack(pady=(20, 4))
        var = ctk.StringVar()
        entry = ctk.CTkEntry(win, textvariable=var, width=260, height=32,
                             font=ctk.CTkFont(size=11),
                             placeholder_text=_('config_profile_name_ph'))
        entry.pack(pady=(0, 12))
        entry.focus()
        def _do_save():
            name = var.get().strip()
            if not name:
                messagebox.showwarning(_('config_profile_save'), _('config_profile_empty'), parent=win)
                return
            self._collect()
            import copy
            self._profiles[name] = copy.deepcopy(self._cfg)
            self._persist_profiles()
            self._profile_menu.configure(values=list(self._profiles.keys()) or [""])
            self._profile_var.set(name)
            messagebox.showinfo(_('config_profile_save'), _('config_profile_saved', name=name), parent=win)
            win.destroy()
        entry.bind("<Return>", lambda _: _do_save())
        ctk.CTkButton(win, text=f"💾  {_('config_profile_save')}", width=140, height=30,
                      command=_do_save).pack()

    def _load_profile(self) -> None:
        """Carrega o perfil selecionado no dropdown."""
        name = self._profile_var.get()
        if not name or name not in self._profiles:
            return
        import copy
        self._cfg = copy.deepcopy(self._profiles[name])
        # Recriar a janela para atualizar todos os widgets com os novos valores
        for widget in self.winfo_children():
            widget.destroy()
        self._build()
        self._profile_var.set(name)
        self._footer_lbl.configure(text=_('config_profile_loaded', name=name))

    def _delete_profile(self) -> None:
        name = self._profile_var.get()
        if not name or name not in self._profiles:
            return
        if messagebox.askyesno(_('config_profile_delete'),
                       _('config_profile_confirm', name=name), parent=self):
            del self._profiles[name]
            self._persist_profiles()
            keys = list(self._profiles.keys())
            self._profile_menu.configure(values=keys or [""])
            self._profile_var.set(keys[0] if keys else "")

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=48)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="⚙️", font=ctk.CTkFont(size=22)
        ).grid(row=0, column=0, padx=(16, 8), pady=8)
        ctk.CTkLabel(hdr, text=_('config_title'),
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(hdr, text=_('config_file_name'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=0, column=2, padx=14)

        # ── Barra de Perfis ───────────────────────────────────────────────────
        pf = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=0, height=40)
        pf.grid(row=1, column=0, sticky="ew")
        pf.grid_propagate(False)
        pf.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(pf, text=_('config_profile_label'),
                     font=ctk.CTkFont(size=10, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=0, padx=(12, 6), pady=8, sticky="w")

        self._profile_var = ctk.StringVar(value="")
        profile_keys = list(self._profiles.keys())
        self._profile_menu = ctk.CTkOptionMenu(
            pf, variable=self._profile_var,
            values=profile_keys if profile_keys else [""],
            width=180, height=26, corner_radius=6,
            fg_color=C["surface"], button_color=C["border"],
            button_hover_color=C["accent"],
            font=ctk.CTkFont(size=10),
        )
        self._profile_menu.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="w")

        ctk.CTkButton(pf, text=f"⬇️ {_('config_profile_load')}", width=90, height=26, corner_radius=6,
                      font=ctk.CTkFont(size=10),
                      fg_color=C["surface"], hover_color=C["border"],
                      command=self._load_profile,
        ).grid(row=0, column=2, padx=(0, 4))
        ctk.CTkButton(pf, text=f"💾 {_('config_profile_save')}", width=80, height=26, corner_radius=6,
                      font=ctk.CTkFont(size=10),
                      command=self._save_profile,
        ).grid(row=0, column=3, padx=(0, 4))
        ctk.CTkButton(pf, text="🗑", width=32, height=26, corner_radius=6,
                      font=ctk.CTkFont(size=11),
                      fg_color=C["surface"], hover_color=C["err_bg"],
                      text_color=C["error"],
                      command=self._delete_profile,
        ).grid(row=0, column=4, padx=(0, 12))

        # ── Tabs ──────────────────────────────────────────────────────────────
        tabs = ctk.CTkTabview(
            self,
            fg_color=C["surface"],
            segmented_button_fg_color=C["surface2"],
            segmented_button_selected_color=C["accent"],
            segmented_button_selected_hover_color=C["accent"],
            segmented_button_unselected_color=C["surface2"],
            segmented_button_unselected_hover_color=C["border"],
        )
        tabs.grid(row=2, column=0, padx=12, pady=(8, 4), sticky="nsew")
        tabs.add(_('config_tab_layers'))
        tabs.add(_('config_tab_text'))
        tabs.add(_('config_tab_drawing'))
        tabs.add(_('tab_extra_rules'))
        self._build_layers_tab(tabs.tab(_('config_tab_layers')))
        self._build_text_tab(tabs.tab(_('config_tab_text')))
        self._build_drawing_tab(tabs.tab(_('config_tab_drawing')))
        self._build_extra_rules_tab(tabs.tab(_('tab_extra_rules')))

        # ── Footer ────────────────────────────────────────────────────────────
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.grid(row=3, column=0, padx=14, pady=(4, 14), sticky="ew")
        ftr.grid_columnconfigure(0, weight=1)
        self._footer_lbl = ctk.CTkLabel(
            ftr, text="", font=ctk.CTkFont(size=10), text_color=C["muted"],
        )
        self._footer_lbl.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            ftr, text=_('config_btn_save'), width=120, height=36, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._save,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            ftr, text=_('config_btn_close'), width=95, height=36, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=12), text_color=C["muted"],
            command=self.destroy,
        ).grid(row=0, column=2)

    # ── Tab: Camadas ──────────────────────────────────────────────────────────

    def _build_layers_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        layers_cfg = self._cfg.get("layers", {})
        self._req_layers: list[str] = list(layers_cfg.get("required") or [])

        # --- Required layers ---
        ctk.CTkLabel(parent, text=_('config_layers_required_title'),
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, sticky="w", pady=(12, 2))
        ctk.CTkLabel(parent,
                 text=_('config_layers_required_hint'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=1, column=0, sticky="w", pady=(0, 6))

        lf = ctk.CTkFrame(parent, fg_color=C["surface2"], corner_radius=8)
        lf.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        lf.grid_columnconfigure(0, weight=1)

        self._layers_lb = tk.Listbox(
            lf, bg=C["surface2"], fg=C["text"],
            selectbackground=C["border"], selectforeground=C["text"],
            borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 10), height=5,
        )
        self._layers_lb.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 4))
        for layer in self._req_layers:
            self._layers_lb.insert("end", layer)

        add_row = ctk.CTkFrame(lf, fg_color="transparent")
        add_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        add_row.grid_columnconfigure(0, weight=1)

        self._new_layer_var = ctk.StringVar()
        new_entry = ctk.CTkEntry(
            add_row, textvariable=self._new_layer_var,
            placeholder_text=_('config_layer_name_ph'),
            height=30, corner_radius=6, font=ctk.CTkFont(size=11),
            fg_color=C["surface"], border_color=C["border"],
        )
        new_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        new_entry.bind("<Return>", lambda _: self._add_layer())

        ctk.CTkButton(add_row, text=_('config_btn_add_layer'), width=100, height=30,
                      corner_radius=6, font=ctk.CTkFont(size=11),
                      command=self._add_layer,
        ).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(add_row, text=_('config_btn_remove_layer'), width=90, height=30,
                      corner_radius=6, font=ctk.CTkFont(size=11),
                      fg_color=C["surface"], hover_color=C["border"],
                      text_color=C["muted"], command=self._remove_layer,
        ).grid(row=0, column=2)

        # --- Naming convention ---
        ctk.CTkLabel(parent, text=_('config_naming_title'),
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=3, column=0, sticky="w", pady=(12, 2))
        ctk.CTkLabel(parent,
                     text=_('config_naming_hint'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"], justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(0, 6))

        self._naming_var = ctk.StringVar(
            value=layers_cfg.get("naming_convention") or "")
        ctk.CTkEntry(parent, textvariable=self._naming_var,
                     placeholder_text=_('config_naming_ph'),
                     height=34, corner_radius=8, font=ctk.CTkFont(size=11),
                     fg_color=C["surface2"], border_color=C["border"],
        ).grid(row=5, column=0, sticky="ew")

    def _add_layer(self) -> None:
        name = self._new_layer_var.get().strip().upper()
        if name and name not in self._req_layers:
            self._req_layers.append(name)
            self._layers_lb.insert("end", name)
            self._new_layer_var.set("")

    def _remove_layer(self) -> None:
        sel = self._layers_lb.curselection()
        if sel:
            self._layers_lb.delete(sel[0])
            del self._req_layers[sel[0]]

    # ── Tab: Textos ───────────────────────────────────────────────────────────

    def _build_text_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        text_cfg = self._cfg.get("text", {})

        ctk.CTkLabel(parent, text=_('config_text_heights_title'),
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(12, 8))

        # --- Reference table ---
        ref = ctk.CTkFrame(parent, fg_color=C["surface2"], corner_radius=8)
        ref.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 20))

        headers = [(_('config_text_col_type'), 230), (_('config_text_col_min'), 70), (_('config_text_col_max'), 70)]
        for col, (h, w) in enumerate(headers):
            ctk.CTkLabel(ref, text=h, font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=C["muted"], width=w, anchor="w"
            ).grid(row=0, column=col, padx=(10, 4), pady=(6, 2), sticky="w")

        for i, (tipo, mn, mx) in enumerate([
            (_('config_text_ref_topo_utm'), "0.50", "20.0"),
            (_('config_text_ref_arch_150'), "1.50", "10.0"),
            (_('config_text_ref_struct_civil'), "0.10", "5.0"),
            (_('config_text_ref_mech_industrial'), "2.00", "15.0"),
            (_('config_text_ref_topo_survey'), "0.03", "50.0"),
        ]):
            fg = C["surface"] if i % 2 else C["surface2"]
            for col, (val, clr, w) in enumerate([
                (tipo, C["muted"],   230),
                (mn,   C["success"], 70),
                (mx,   C["error"],   70),
            ]):
                ctk.CTkLabel(ref, text=val, font=ctk.CTkFont(size=10),
                             text_color=clr, width=w, anchor="w",
                ).grid(row=i + 1, column=col, padx=(10, 4), pady=3, sticky="w")

        # --- Min / Max entries ---
        for col_off, (label, key, attr, clr) in enumerate([
            (_('config_text_min_height'), "min_height", "_min_h_var", C["success"]),
            (_('config_text_max_height'), "max_height", "_max_h_var", C["error"]),
        ]):
            c = col_off * 2
            ctk.CTkLabel(parent, text=label,
                         font=ctk.CTkFont(size=12, weight="bold"), text_color=clr,
            ).grid(row=2, column=c, sticky="w", padx=(0 if c == 0 else 20, 0))
            var = ctk.StringVar(value=str(text_cfg.get(key, "")))
            setattr(self, attr, var)
            ctk.CTkEntry(parent, textvariable=var,
                         width=130, height=40, corner_radius=8,
                         font=ctk.CTkFont(size=16),
                         fg_color=C["surface2"], border_color=clr,
            ).grid(row=3, column=c, sticky="w", padx=(0 if c == 0 else 20, 0), pady=(4, 0))

        ctk.CTkLabel(parent,
                     text=_('config_text_units_hint'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"],
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(12, 0))

    # ── Tab: Desenho ──────────────────────────────────────────────────────────

    def _build_drawing_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        drawing_cfg = self._cfg.get("drawing", {})
        self._drawing_vars: dict[str, ctk.BooleanVar] = {}

        RULES = [
            ("check_entities_on_layer_0",
               _('cfg_rule_layer0_label'),
               _('cfg_rule_layer0_desc')),
            ("check_unused_blocks",
               _('cfg_rule_unused_blocks_label'),
               _('cfg_rule_unused_blocks_desc')),
            ("check_empty_layers",
               _('cfg_rule_empty_layers_label'),
               _('cfg_rule_empty_layers_desc')),
            ("check_frozen_layers",
               _('cfg_rule_frozen_layers_label'),
               _('cfg_rule_frozen_layers_desc')),
            ("check_off_layers",
               _('cfg_rule_off_layers_label'),
               _('cfg_rule_off_layers_desc')),
            ("check_color_bylayer",
               _('cfg_rule_color_bylayer_label'),
               _('cfg_rule_color_bylayer_desc')),
            ("check_linetype_bylayer",
               _('cfg_rule_linetype_bylayer_label'),
               _('cfg_rule_linetype_bylayer_desc')),
            ("check_duplicates",
               _('cfg_rule_duplicates_label'),
               _('cfg_rule_duplicates_desc')),
            ("check_xrefs",
               _('cfg_rule_xrefs_label'),
               _('cfg_rule_xrefs_desc')),
        ]

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, pady=(6, 0))
        scroll.grid_columnconfigure(0, weight=1)

        for i, (key, label, desc) in enumerate(RULES):
            val = drawing_cfg.get(key, True)
            var = ctk.BooleanVar(value=bool(val))
            self._drawing_vars[key] = var

            row_f = ctk.CTkFrame(
                scroll,
                fg_color=C["surface2"] if i % 2 == 0 else C["surface"],
                corner_radius=8,
            )
            row_f.pack(fill="x", pady=3)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkSwitch(
                row_f, variable=var, text="",
                width=44, button_color=C["accent"], progress_color=C["accent"],
                fg_color=C["border"],
            ).grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=10)

            ctk.CTkLabel(row_f, text=label,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C["text"], anchor="w",
            ).grid(row=0, column=1, sticky="w", pady=(8, 0))
            ctk.CTkLabel(row_f, text=desc,
                         font=ctk.CTkFont(size=10), text_color=C["muted"],
                         anchor="w", wraplength=380,
            ).grid(row=1, column=1, sticky="w", pady=(0, 8))

    # ── Tab: Novas Regras ─────────────────────────────────────────────────────

    def _build_extra_rules_tab(self, parent) -> None:
        """Tab com as 6 novas regras v2.5 — toggle + severity override."""
        parent.grid_columnconfigure(0, weight=1)
        drawing_cfg = self._cfg.get("drawing", {})
        rules_cfg   = self._cfg.get("rules", {}).get("severity_overrides", {})
        self._extra_rule_vars: dict[str, ctk.BooleanVar] = {}
        self._sev_vars:        dict[str, ctk.StringVar]  = {}

        SEV_OPTIONS = [_('sev_inherit'), "ERROR", "WARNING", "INFO"]

        EXTRA_RULES = [
            ("check_title_block",    "TITLE_BLOCK_MISSING",
               _('cfg_extra_title_block_label'),
               _('cfg_extra_title_block_desc')),
            ("check_viewport",       "VIEWPORT_NO_SCALE",
               _('cfg_extra_viewport_scale_label'),
               _('cfg_extra_viewport_scale_desc')),
            ("check_mtext_overflow", "MTEXT_OVERFLOW",
               _('cfg_extra_mtext_overflow_label'),
               _('cfg_extra_mtext_overflow_desc')),
            ("check_external_fonts", "EXTERNAL_FONT",
               _('cfg_extra_external_fonts_label'),
               _('cfg_extra_external_fonts_desc')),
            ("check_line_weights",   "LINEWEIGHT_NOT_BYLAYER",
               _('cfg_extra_lineweight_label'),
               _('cfg_extra_lineweight_desc')),
            ("check_plot_styles",    "PLOT_STYLE_NOT_SET",
               _('cfg_extra_plot_style_label'),
               _('cfg_extra_plot_style_desc')),
        ]

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, pady=(6, 0))
        scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            scroll,
            text=_('extra_rules_header'),
            font=ctk.CTkFont(size=10), text_color=C["muted"],
        ).pack(anchor="w", padx=8, pady=(4, 8))

        for i, (cfg_key, rule_id, label, desc) in enumerate(EXTRA_RULES):
            val = drawing_cfg.get(cfg_key, True)
            var = ctk.BooleanVar(value=bool(val))
            self._extra_rule_vars[cfg_key] = var

            cur_sev = rules_cfg.get(rule_id, "")
            svar = ctk.StringVar(value=cur_sev if cur_sev in ("ERROR", "WARNING", "INFO") else _('sev_inherit'))
            self._sev_vars[rule_id] = svar

            row_f = ctk.CTkFrame(
                scroll,
                fg_color=C["surface2"] if i % 2 == 0 else C["surface"],
                corner_radius=8,
            )
            row_f.pack(fill="x", pady=3)
            row_f.grid_columnconfigure(1, weight=1)

            ctk.CTkSwitch(
                row_f, variable=var, text="",
                width=44, button_color=C["accent"], progress_color=C["accent"],
                fg_color=C["border"],
            ).grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=10)

            ctk.CTkLabel(row_f, text=label,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=C["text"], anchor="w",
            ).grid(row=0, column=1, sticky="w", pady=(8, 0))
            ctk.CTkLabel(row_f, text=desc,
                         font=ctk.CTkFont(size=10), text_color=C["muted"],
                         anchor="w", wraplength=330,
            ).grid(row=1, column=1, sticky="w", pady=(0, 8))

            sev_frame = ctk.CTkFrame(row_f, fg_color="transparent")
            sev_frame.grid(row=0, column=2, rowspan=2, padx=(4, 12), pady=10)
            ctk.CTkLabel(sev_frame, text=_('config_severity_label'),
                         font=ctk.CTkFont(size=9), text_color=C["muted"]
            ).pack(anchor="w")
            ctk.CTkOptionMenu(
                sev_frame,
                values=SEV_OPTIONS,
                variable=svar,
                width=100, height=26,
                font=ctk.CTkFont(size=10),
                fg_color=C["surface"],
                button_color=C["border"],
                button_hover_color=C["accent"],
            ).pack()


# ── Watch Folder Window ───────────────────────────────────────────────────────

class WatchFolderWindow(ctk.CTkToplevel):
    """Monitora uma pasta em background e verifica novos/modificados DXF automaticamente."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title(_('watch_title'))
        self.geometry("720x500")
        self.configure(fg_color=C["bg"])
        self.resizable(True, True)
        self._watching   = False
        self._watch_thread: threading.Thread | None = None
        self._stop_evt   = threading.Event()
        self._seen_files: dict[str, float] = {}   # caminho → mtime
        self._html_map:   dict[str, str | None] = {}
        _apply_style()
        self._build()
        self.lift()
        self.focus()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Pasta + controles ────────────────────────────────────────────────
        fc = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        fc.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")
        fc.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(fc, text="👁️", font=ctk.CTkFont(size=20)
        ).grid(row=0, column=0, padx=(14, 8), pady=10)
        ctk.CTkLabel(fc, text=_('watch_header'),
                     font=ctk.CTkFont(size=13, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(fc, text=_('watch_flow_hint'),
                 font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=0, column=2, columnspan=2, padx=(8, 8), sticky="w")

        self._folder_var = ctk.StringVar()
        ctk.CTkEntry(fc, textvariable=self._folder_var,
                     placeholder_text=_('watch_placeholder'),
                     height=30, corner_radius=8,
                     fg_color=C["surface2"], border_color=C["border"],
                     font=ctk.CTkFont(size=11),
        ).grid(row=1, column=0, columnspan=3, padx=(14, 8), pady=(0, 6), sticky="ew")

        ar = ctk.CTkFrame(fc, fg_color="transparent")
        ar.grid(row=2, column=0, columnspan=4, padx=12, pady=(0, 10), sticky="ew")
        ar.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(ar, text=_('watch_btn_folder'), width=82, height=28, corner_radius=8,
                      command=self._browse,
        ).grid(row=0, column=0, padx=(0, 6))

        self._open_folder_btn = ctk.CTkButton(
            ar, text=_('btn_open_folder'), width=82, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._open_folder,
        )
        self._open_folder_btn.grid(row=0, column=1, padx=(0, 6))

        self._watch_btn = ctk.CTkButton(
            ar, text=_('watch_btn_start'), width=160, height=28, corner_radius=8,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._toggle_watch,
        )
        self._watch_btn.grid(row=0, column=2, padx=(0, 8))

        self._clear_watch_btn = ctk.CTkButton(
            ar, text=_('watch_btn_clear'), width=72, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._clear_rows,
        )
        self._clear_watch_btn.grid(row=0, column=3, padx=(0, 8))

        # Intervalo de verificação
        ctk.CTkLabel(ar, text=_('watch_interval_lbl'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=0, column=4, padx=(0, 4))
        self._interval_var = ctk.StringVar(value="10")
        ctk.CTkEntry(ar, textvariable=self._interval_var,
                     width=52, height=28, corner_radius=6,
                     font=ctk.CTkFont(size=11),
                     fg_color=C["surface2"], border_color=C["border"],
        ).grid(row=0, column=5, sticky="w")

        self._status_lbl = ctk.CTkLabel(
            ar, text=_('watch_status_stopped'),
            font=ctk.CTkFont(size=10), text_color=C["muted"],
        )
        self._status_lbl.grid(row=0, column=6, padx=(14, 0), sticky="w")

        # ── Tabela de resultados ─────────────────────────────────────────────
        tc = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        tc.grid(row=2, column=0, padx=12, pady=(0, 6), sticky="nsew")
        tc.grid_columnconfigure(0, weight=1)
        tc.grid_rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            tc,
            columns=("time", "file", "status", "errors", "warnings"),
            show="headings", style="DWG.Treeview", selectmode="browse",
        )
        for col, title, w, anchor in [
            ("time",     _('watch_col_time'),     90, "center"),
            ("file",     _('watch_col_file'), 300, "w"),
            ("status",   _('watch_col_status'),   90, "center"),
            ("errors",   _('watch_col_errors'),    60, "center"),
            ("warnings", _('watch_col_warnings'),   60, "center"),
        ]:
            self._tree.heading(col, text=title)
            self._tree.column(col, width=w, minwidth=40, anchor=anchor)

        self._tree.tag_configure("pass", foreground=C["success"])
        self._tree.tag_configure("fail", foreground=C["error"])
        self._tree.tag_configure("alt",  background="#1e2235")
        self._tree.bind("<Double-1>", lambda _: self._open_report())

        vsb = ctk.CTkScrollbar(tc, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        vsb.grid(row=0, column=1, sticky="ns", pady=8)

        ctk.CTkLabel(self, text=_('watch_dblclick'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=3, column=0, pady=(0, 8))

    # ── Lógica ───────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        d = filedialog.askdirectory(title=_('watch_select_folder'))
        if d:
            self._folder_var.set(d)

    def _toggle_watch(self) -> None:
        if self._watching:
            self._stop_watch()
        else:
            self._start_watch()

    def _start_watch(self) -> None:
        folder = self._folder_var.get().strip()
        if not folder or not Path(folder).exists():
            messagebox.showwarning(_('watch_invalid_folder'),
                                   _('watch_invalid_msg'), parent=self)
            return
        try:
            interval = max(3, int(self._interval_var.get()))
        except ValueError:
            interval = 10
        self._interval_var.set(str(interval))
        self._watching = True
        self._stop_evt.clear()
        # Indexa os arquivos já existentes para não re-verificar no primeiro scan
        self._seen_files = {
            str(f): f.stat().st_mtime
            for f in Path(folder).rglob("*.dxf")
        }
        self._watch_btn.configure(text=_('watch_btn_stop'),
                                   fg_color=C["err_bg"], hover_color=C["error"],
                                   text_color=C["error"])
        self._status_lbl.configure(text=_('watch_status_running', interval=interval),
                                   text_color=C["success"])
        self._watch_thread = threading.Thread(
            target=self._watch_worker, args=(folder, interval), daemon=True)
        self._watch_thread.start()

    def _stop_watch(self) -> None:
        self._watching = False
        self._stop_evt.set()
        self._watch_btn.configure(text=_('watch_btn_start'),
                                   fg_color=C["accent"], hover_color=C["accent"],
                                   text_color="white")
        self._status_lbl.configure(text=_('watch_status_stopped'), text_color=C["muted"])

    def _watch_worker(self, folder: str, interval: int) -> None:
        while not self._stop_evt.wait(interval):
            try:
                current = {
                    str(f): f.stat().st_mtime
                    for f in Path(folder).rglob("*.dxf")
                }
                new_or_changed = [
                    fp for fp, mt in current.items()
                    if fp not in self._seen_files or self._seen_files[fp] != mt
                ]
                self._seen_files = current
                for fp in new_or_changed:
                    self.after(0, self._notify_new_file, fp)
                    try:
                        result = DXFChecker().check(fp)
                        base   = str(Path(fp).parent / (Path(fp).stem + "_report"))
                        html   = generate_html_report(result, base + ".html")
                        _add_to_history(result, html)
                        self.after(0, self._add_result_row, fp, result, html)
                    except Exception as exc:
                        logging.error("Watch: erro ao processar '%s': %s", fp, exc)
                        self.after(0, self._add_error_row, fp, str(exc))
            except Exception as exc:
                logging.error("Watch: erro no scan: %s", exc)

    def _notify_new_file(self, fp: str) -> None:
        self._status_lbl.configure(
            text=_('watch_status_check', file=Path(fp).name), text_color=C["warning"])

    def _add_result_row(self, fp: str, result: dict, html: str | None) -> None:
        tag  = "pass" if result["passed"] else "fail"
        idx  = len(self._tree.get_children())
        tags = (tag, "alt") if idx % 2 else (tag,)
        iid  = str(idx)
        self._html_map[iid] = html
        self._tree.insert("", 0, iid=iid, values=(
            datetime.now().strftime("%H:%M:%S"),
            Path(fp).name,
            _('watch_passed') if result["passed"] else _('watch_failed'),
            result["errors"], result["warnings"],
        ), tags=tags)
        self._status_lbl.configure(
            text=_('watch_status_last', file=Path(fp).name), text_color=C["success"])
        # ── Notificação desktop ───────────────────────────────────────────────
        fname = Path(fp).name
        if result["passed"]:
            msg = f"{fname}  —  {_('notify_pass')}"
        else:
            msg = f"{fname}  —  {_('notify_fail', n=result['errors'])}"
        threading.Thread(
            target=_show_toast, args=("DWG Quality Checker", msg), daemon=True
        ).start()

    def _add_error_row(self, fp: str, msg: str) -> None:
        idx = len(self._tree.get_children())
        self._tree.insert("", 0, iid=str(idx), values=(
            datetime.now().strftime("%H:%M:%S"),
            Path(fp).name, _('watch_error_row'), "—", "—",
        ), tags=("fail",))

    def _open_report(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        html = self._html_map.get(sel[0])
        if html and Path(html).exists():
            webbrowser.open(f"file:///{Path(html).resolve()}")
        else:
            messagebox.showinfo(_('common_not_found_title'), _('common_report_not_found'), parent=self)

    def _on_close(self) -> None:
        self._stop_watch()
        self.destroy()

    def _open_folder(self) -> None:
        folder = self._folder_var.get().strip()
        if folder and Path(folder).exists():
            os.startfile(str(Path(folder).resolve()))

    def _clear_rows(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._html_map.clear()
        self._status_lbl.configure(text=_('watch_status_stopped'), text_color=C["muted"])


# ── Revision Comparison Window ────────────────────────────────────────────────

class CompareWindow(ctk.CTkToplevel):
    """Compara dois arquivos DXF e exibe as diferenças entre revisões."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title(_('compare_title'))
        self.geometry("860x580")
        self.configure(fg_color=C["bg"])
        self.resizable(True, True)
        self._html_map: dict[str, str | None] = {}
        _apply_style()
        self._build()
        self.lift()
        self.focus()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Cabeçalho ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        hdr.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_columnconfigure(3, weight=1)

        def _file_row(col_label, col_entry, col_btn, label, attr):
            ctk.CTkLabel(hdr, text=label,
                         font=ctk.CTkFont(size=10, weight="bold"), text_color=C["muted"]
            ).grid(row=0, column=col_label, padx=(14, 6), pady=10, sticky="w")
            var = ctk.StringVar()
            setattr(self, attr, var)
            ctk.CTkEntry(hdr, textvariable=var,
                         placeholder_text=_('compare_file_ph'),
                         height=30, corner_radius=8,
                         fg_color=C["surface2"], border_color=C["border"],
                         font=ctk.CTkFont(size=11),
            ).grid(row=0, column=col_entry, padx=(0, 6), pady=10, sticky="ew")
            ctk.CTkButton(hdr, text="📂", width=36, height=30, corner_radius=8,
                          command=lambda a=attr: self._browse_file(a),
            ).grid(row=0, column=col_btn, padx=(0, 10), pady=10)

        _file_row(0, 1, 2, _('compare_file_a'), "_file_a")
        _file_row(4, 5, 6, _('compare_file_b'), "_file_b")

        ctk.CTkLabel(hdr,
             text=_('compare_flow_hint'),
                 font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=1, column=0, columnspan=7, padx=12, pady=(0, 4), sticky="w")

        ar = ctk.CTkFrame(hdr, fg_color="transparent")
        ar.grid(row=2, column=0, columnspan=7, padx=12, pady=(0, 10), sticky="ew")
        ar.grid_columnconfigure(2, weight=1)

        self._compare_btn = ctk.CTkButton(
            ar, text=_('compare_btn'), width=130, height=32, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._compare,
        )
        self._compare_btn.grid(row=0, column=0, padx=(0, 12))

        ctk.CTkButton(
            ar, text=_('btn_swap'), width=86, height=30, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), command=self._swap_files,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            ar, text=_('btn_clear'), width=78, height=30, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), command=self._clear_compare,
        ).grid(row=0, column=2, padx=(0, 10))

        self._cmp_status = ctk.CTkLabel(
            ar, text=_('compare_select_msg'),
            font=ctk.CTkFont(size=11), text_color=C["muted"],
        )
        self._cmp_status.grid(row=0, column=3, sticky="w")

        # Badges de diferenças
        bg = ctk.CTkFrame(ar, fg_color="transparent")
        bg.grid(row=0, column=4)
        self._add_b  = self._badge(bg, "➕ 0", C["success"], "#0d2e1a", 0)
        self._rem_b  = self._badge(bg, "➖ 0", C["error"],   C["err_bg"],  1)
        self._mod_b  = self._badge(bg, "✏️ 0",  C["warning"], C["warn_bg"], 2)

        # ── Tabela de diff ───────────────────────────────────────────────────
        tc = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        tc.grid(row=2, column=0, padx=12, pady=(0, 6), sticky="nsew")
        tc.grid_columnconfigure(0, weight=1)
        tc.grid_rowconfigure(0, weight=1)

        # Filtro
        flt = ctk.CTkFrame(tc, fg_color="transparent")
        flt.grid(row=0, column=0, columnspan=2, padx=12, pady=(8, 4), sticky="ew")
        flt.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(flt, text=_('compare_diff_label'),
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        self._diff_sev = ctk.StringVar(value=_('compare_filter_all'))
        ctk.CTkSegmentedButton(
            flt, values=[_('compare_filter_all'), _('compare_filter_add'), _('compare_filter_rem'), _('compare_filter_mod')],
            variable=self._diff_sev, height=24,
            font=ctk.CTkFont(size=9, weight="bold"),
            command=lambda _: self._apply_diff_filter(),
        ).grid(row=0, column=2)

        inner = ctk.CTkFrame(tc, fg_color=C["surface2"], corner_radius=8)
        inner.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        tc.grid_rowconfigure(1, weight=1)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(0, weight=1)

        self._diff_tree = ttk.Treeview(
            inner,
            columns=("tipo", "layer", "handle", "detalhe"),
            show="headings", style="DWG.Treeview", selectmode="browse",
        )
        for col, title, w, anchor in [
            ("tipo",    _('compare_col_type'),       110, "center"),
            ("layer",   _('compare_col_layer'),      140, "w"),
            ("handle",  _('compare_col_handle'),      80, "center"),
            ("detalhe", _('compare_col_detail'),    440, "w"),
        ]:
            self._diff_tree.heading(col, text=title)
            self._diff_tree.column(col, width=w, minwidth=40, anchor=anchor)

        self._diff_tree.tag_configure("added",    foreground=C["success"])
        self._diff_tree.tag_configure("removed",  foreground=C["error"])
        self._diff_tree.tag_configure("modified", foreground=C["warning"])
        self._diff_tree.tag_configure("alt",      background="#1e2235")

        vsb = ctk.CTkScrollbar(inner, command=self._diff_tree.yview)
        self._diff_tree.configure(yscrollcommand=vsb.set)
        self._diff_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        vsb.grid(row=0, column=1, sticky="ns", pady=8)

        self._all_diff_rows: list[tuple] = []

    @staticmethod
    def _badge(parent, text, fg, bg, col):
        lbl = ctk.CTkLabel(parent, text=text,
                           font=ctk.CTkFont(size=10, weight="bold"),
                           fg_color=bg, corner_radius=5,
                           text_color=fg, padx=8, pady=2)
        lbl.grid(row=0, column=col, padx=(0, 4))
        return lbl

    def _browse_file(self, attr: str) -> None:
        p = filedialog.askopenfilename(
            title=_('compare_select_file_title'),
            filetypes=[("DXF", "*.dxf"), ("Todos", "*.*")],
        )
        if p:
            getattr(self, attr).set(p)
            self._cmp_status.configure(text=_('compare_selected', file=Path(p).name), text_color=C["muted"])

    def _swap_files(self) -> None:
        a = self._file_a.get()
        b = self._file_b.get()
        self._file_a.set(b)
        self._file_b.set(a)

    def _clear_compare(self) -> None:
        self._file_a.set("")
        self._file_b.set("")
        self._all_diff_rows = []
        self._diff_tree.delete(*self._diff_tree.get_children())
        self._diff_sev.set(_('compare_filter_all'))
        self._add_b.configure(text="➕ 0")
        self._rem_b.configure(text="➖ 0")
        self._mod_b.configure(text="✏️ 0")
        self._cmp_status.configure(text=_('compare_select_msg'), text_color=C["muted"])

    def _compare(self) -> None:
        fa = self._file_a.get().strip()
        fb = self._file_b.get().strip()
        if not fa or not fb:
            messagebox.showwarning(_('compare_no_files'),
                                   _('compare_no_files_msg'), parent=self)
            return
        for fp in (fa, fb):
            if not Path(fp).exists():
                messagebox.showwarning(_('compare_not_found'),
                                       f"{_('compare_not_found')}:\n{fp}", parent=self)
                return

        self._compare_btn.configure(state="disabled", text=_('compare_btn_loading'))
        self._cmp_status.configure(text=_('compare_loading_msg'), text_color=C["muted"])
        threading.Thread(target=self._compare_worker, args=(fa, fb), daemon=True).start()

    def _compare_worker(self, fa: str, fb: str) -> None:
        try:
            import ezdxf
            doc_a = ezdxf.readfile(fa)
            doc_b = ezdxf.readfile(fb)

            # Indexa entidades por handle e por (tipo, layer, coords-hash)
            def _index(doc):
                idx = {}
                for e in doc.modelspace():
                    h = e.dxf.get("handle", "")
                    try:
                        coords = str(round(e.dxf.get("insert", (0,0,0))[0], 3)) if hasattr(e.dxf, "insert") else ""
                    except Exception:
                        coords = ""
                    key = f"{e.dxftype()}|{e.dxf.get('layer','0')}|{h}"
                    idx[key] = {
                        "handle": h,
                        "layer":  e.dxf.get("layer", "0"),
                        "type":   e.dxftype(),
                        "coords": coords,
                    }
                return idx

            idx_a = _index(doc_a)
            idx_b = _index(doc_b)

            keys_a = set(idx_a)
            keys_b = set(idx_b)

            added    = [(idx_b[k], "added")    for k in keys_b - keys_a]
            removed  = [(idx_a[k], "removed")  for k in keys_a - keys_b]
            # Modificados: mesma entidade (handle) mas com diferença de layer/coords
            handles_a = {v["handle"]: v for v in idx_a.values() if v["handle"]}
            handles_b = {v["handle"]: v for v in idx_b.values() if v["handle"]}
            modified = []
            for h, va in handles_a.items():
                if h in handles_b:
                    vb = handles_b[h]
                    if va["layer"] != vb["layer"] or va["coords"] != vb["coords"]:
                        modified.append((vb, "modified",
                                         f"Layer: {va['layer']} → {vb['layer']}" if va["layer"] != vb["layer"]
                                         else f"Posição alterada"))

            self.after(0, self._show_diff, added, removed, modified,
                       Path(fa).name, Path(fb).name)
        except Exception as exc:
            tb = traceback.format_exc()
            logging.error("Comparação: erro:\n%s", tb)
            self.after(0, self._cmp_error, str(exc))

    def _show_diff(self, added, removed, modified, name_a, name_b) -> None:
        self._compare_btn.configure(state="normal", text=_('compare_btn'))
        total = len(added) + len(removed) + len(modified)

        self._add_b.configure(text=f"➕ {len(added)}")
        self._rem_b.configure(text=f"➖ {len(removed)}")
        self._mod_b.configure(text=f"✏️ {len(modified)}")

        self._cmp_status.configure(
            text=_('compare_result_msg', name_a=name_a, name_b=name_b, total=total) if total else _('compare_no_diff', name_a=name_a, name_b=name_b),
            text_color=C["text"] if total else C["success"],
        )

        # Montar lista interna para o filtro
        self._all_diff_rows = []
        for info, tag in added:
            self._all_diff_rows.append((
                _('compare_filter_add'), tag, info["layer"], info["handle"],
                _('compare_added_detail', type=info['type']),
            ))
        for info, tag in removed:
            self._all_diff_rows.append((
                _('compare_filter_rem'), tag, info["layer"], info["handle"],
                _('compare_removed_detail', type=info['type']),
            ))
        for info, tag, detail in modified:
            self._all_diff_rows.append((
                _('compare_filter_mod'), tag, info["layer"], info["handle"], detail,
            ))

        self._apply_diff_filter()

    def _apply_diff_filter(self) -> None:
        self._diff_tree.delete(*self._diff_tree.get_children())
        flt = self._diff_sev.get()
        for idx, row in enumerate(self._all_diff_rows):
            tipo, tag, layer, handle, detalhe = row
            if flt != _('compare_filter_all') and tipo != flt:
                continue
            tags = (tag, "alt") if idx % 2 else (tag,)
            self._diff_tree.insert("", "end", values=(tipo, layer, handle, detalhe),
                                   tags=tags)

    def _cmp_error(self, msg: str) -> None:
        self._compare_btn.configure(state="normal", text=_('compare_btn'))
        self._cmp_status.configure(text=_('compare_error_prefix', msg=msg), text_color=C["error"])
        messagebox.showerror(_('compare_error_title'), msg, parent=self)


# ── Auto-Update checker ───────────────────────────────────────────────────────

_UPDATE_URL = "https://api.github.com/repos/vantaratech/dwg-quality-checker/releases/latest"
# Para usar: crie um release no GitHub com tag "v2.4.0" e o JSON retornará
# {"tag_name": "v2.4.0", "html_url": "...", "body": "changelog..."}


def _check_for_update(current_version: str, callback) -> None:
    """Verifica no GitHub se há uma versão mais recente. Executa callback(info) ou callback(None)."""
    def _worker():
        try:
            req = urllib.request.Request(
                _UPDATE_URL,
                headers={"User-Agent": f"DWGQualityChecker/{current_version}"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode())
            tag      = data.get("tag_name", "").lstrip("v")
            html_url = data.get("html_url", "")
            body     = data.get("body", "")
            if tag and tag != current_version:
                callback({"version": tag, "url": html_url, "changelog": body})
            else:
                callback(None)
        except Exception as exc:
            logging.info("Auto-update: falha ao verificar: %s", exc)
            callback(None)
    threading.Thread(target=_worker, daemon=True).start()


# ── Main Application ──────────────────────────────────────────────────────────

class App(ctk.CTk):
    _PROFILES_FILE = _BASE_DIR / "config_profiles.json"
    _BASE_PROFILE_LABEL = "config.yaml (base)"

    def __init__(self) -> None:
        super().__init__()
        # Inicializa suporte a drag & drop antes de qualquer widget
        if _DND_OK:
            try:
                _tkdnd.TkinterDnD._require(self)
            except Exception as _e:
                logging.warning("DnD: falha ao carregar tkdnd: %s", _e)

        self.title(f"DWG Quality Checker  v{VERSION}")
        self.geometry("1020x680")
        self.minsize(800, 560)
        self.configure(fg_color=C["bg"])

        self._html_path:  str | None = None
        self._csv_path:   str | None = None
        self._pdf_path:   str | None = None
        self._xlsx_path:  str | None = None
        self._all_issues: list       = []
        self.auto_open_var = ctk.BooleanVar(value=True)
        self._profiles_runtime: dict = self._load_runtime_profiles()

        _apply_style()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_controls()
        self._build_results()
        self._build_footer()
        self._setup_shortcuts()
        self._setup_dnd()
        # Verifica atualização em background (silencioso se offline)
        _check_for_update(VERSION, lambda info: self.after(0, self._on_update_result, info))

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        h = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=50)
        h.grid(row=0, column=0, sticky="ew")
        h.grid_propagate(False)
        h.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(h, text="🏗️", font=ctk.CTkFont(size=22)
        ).grid(row=0, column=0, padx=(18, 8), pady=8)

        ctk.CTkLabel(h, text=_('app_name'),
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=1, sticky="w")

        self._btn_history = ctk.CTkButton(
            h, text=_('btn_history'), width=105, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_history,
        )
        self._btn_history.grid(row=0, column=2, padx=(0, 6))

        self._btn_watch = ctk.CTkButton(
            h, text=_('btn_watch'), width=88, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_watch,
        )
        self._btn_watch.grid(row=0, column=3, padx=(0, 6))

        self._btn_compare = ctk.CTkButton(
            h, text=_('btn_compare'), width=100, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_compare,
        )
        self._btn_compare.grid(row=0, column=4, padx=(0, 6))

        self._btn_config = ctk.CTkButton(
            h, text=_('btn_config'), width=90, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_config,
        )
        self._btn_config.grid(row=0, column=5, padx=(0, 6))

        self._btn_about = ctk.CTkButton(
            h, text=_('btn_about'), width=85, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_about,
        )
        self._btn_about.grid(row=0, column=6, padx=(0, 14))

        self._btn_diag = ctk.CTkButton(
            h, text=_('btn_diag'), width=120, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_diagnostics,
        )
        self._btn_diag.grid(row=0, column=7, padx=(0, 10))

    # ── Controls ──────────────────────────────────────────────────────────────

    def _build_controls(self) -> None:
        card = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        card.grid(row=1, column=0, padx=12, pady=(8, 4), sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # ── Row 0: file picker ────────────────────────────────────────────────
        ctk.CTkLabel(card, text=_('label_file'),
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=0, padx=(14, 8), pady=(12, 6), sticky="w")

        fr = ctk.CTkFrame(card, fg_color="transparent")
        fr.grid(row=0, column=1, columnspan=6, padx=(0, 14), pady=(12, 6), sticky="ew")
        fr.grid_columnconfigure(0, weight=1)

        self.file_var = ctk.StringVar()
        self._file_entry = ctk.CTkEntry(
            fr, textvariable=self.file_var,
            placeholder_text=_('file_placeholder'),
            height=32, corner_radius=8,
            fg_color=C["surface2"], border_color=C["border"],
            font=ctk.CTkFont(size=11),
        )
        self._file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._btn_open = ctk.CTkButton(
            fr, text=_('btn_open'), width=90, height=32, corner_radius=8,
            command=self._browse,
        )
        self._btn_open.grid(row=0, column=1, padx=(0, 4))

        self._btn_batch = ctk.CTkButton(
            fr, text=_('btn_folder'), width=80, height=32, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11),
            command=self._open_batch,
        )
        self._btn_batch.grid(row=0, column=2)

        self._btn_clear = ctk.CTkButton(
            fr, text=_('btn_clear'), width=70, height=32, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11),
            command=self._clear_selection,
        )
        self._btn_clear.grid(row=0, column=3, padx=(4, 0))

        ctk.CTkLabel(
            card,
            text=_('main_flow_hint'),
            font=ctk.CTkFont(size=10),
            text_color=C["muted"],
        ).grid(row=1, column=0, columnspan=7, padx=14, pady=(0, 6), sticky="w")

        # ── Row 1: action ─────────────────────────────────────────────────────
        ar = ctk.CTkFrame(card, fg_color="transparent")
        ar.grid(row=2, column=0, columnspan=7, padx=14, pady=(0, 12), sticky="ew")
        ar.grid_columnconfigure(3, weight=1)

        self.run_btn = ctk.CTkButton(
            ar, text=_('btn_verify'),
            width=125, height=32, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._run,
        )
        self.run_btn.grid(row=0, column=0, padx=(0, 12))

        self.strict_var = ctk.BooleanVar(value=False)
        self._strict_chk = ctk.CTkCheckBox(ar, text=_('main_strict_label'), variable=self.strict_var,
                           font=ctk.CTkFont(size=11), text_color=C["muted"], width=68)
        self._strict_chk.grid(row=0, column=1, padx=(0, 20))

        ctk.CTkLabel(ar, text=_("config_profile_label"),
                     font=ctk.CTkFont(size=10, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=2, padx=(0, 6), sticky="e")
        profile_values = [self._BASE_PROFILE_LABEL, *sorted(self._profiles_runtime.keys())]
        self._run_profile_var = ctk.StringVar(value=self._BASE_PROFILE_LABEL)
        self._run_profile_menu = ctk.CTkOptionMenu(
            ar,
            variable=self._run_profile_var,
            values=profile_values,
            width=170,
            height=26,
            corner_radius=6,
            fg_color=C["surface2"],
            button_color=C["border"],
            button_hover_color=C["accent"],
            font=ctk.CTkFont(size=10),
        )
        self._run_profile_menu.grid(row=0, column=3, padx=(0, 10), sticky="w")

        self._run_profiles_multi_var = ctk.StringVar(value="")
        ctk.CTkEntry(
            ar,
            textvariable=self._run_profiles_multi_var,
            width=220,
            height=26,
            corner_radius=6,
            fg_color=C["surface2"],
            border_color=C["border"],
            font=ctk.CTkFont(size=10),
            placeholder_text="NBR_5410, NBR_9050",
        ).grid(row=0, column=4, padx=(0, 10), sticky="w")

        self._status_icon = ctk.CTkLabel(ar, text="⏳", font=ctk.CTkFont(size=15))
        self._status_icon.grid(row=0, column=5, padx=(0, 5))

        self._status_lbl = ctk.CTkLabel(
            ar, text=_('main_status_waiting'),
            font=ctk.CTkFont(size=11), text_color=C["muted"],
        )
        self._status_lbl.grid(row=0, column=6, sticky="w")

        # Badges
        bg = ctk.CTkFrame(ar, fg_color="transparent")
        bg.grid(row=0, column=7, padx=(0, 10))
        self._err_b  = self._badge(bg, "❌ 0", C["error"],   C["err_bg"],  0)
        self._warn_b = self._badge(bg, "⚠️ 0", C["warning"], C["warn_bg"], 1)
        self._info_b = self._badge(bg, "ℹ️ 0", C["info"],    C["info_bg"], 2)

        # Report buttons
        self._html_btn = ctk.CTkButton(
            ar, text=_('btn_html'), width=76, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._open_html, state="disabled",
        )
        self._html_btn.grid(row=0, column=8, padx=(0, 4))

        self._csv_btn = ctk.CTkButton(
            ar, text=_('btn_csv'), width=64, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._open_csv, state="disabled",
        )
        self._csv_btn.grid(row=0, column=9)

        self._pdf_btn = ctk.CTkButton(
            ar, text=_('btn_pdf'), width=64, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._open_pdf, state="disabled",
        )
        self._pdf_btn.grid(row=0, column=10, padx=(4, 0))

        self._xlsx_btn = ctk.CTkButton(
            ar, text=_('btn_xlsx'), width=72, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._open_xlsx, state="disabled",
        )
        self._xlsx_btn.grid(row=0, column=11, padx=(4, 0))

        self._ann_btn = ctk.CTkButton(
            ar, text=_('btn_annotate'), width=95, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._annotate_dxf, state="disabled",
        )
        self._ann_btn.grid(row=0, column=12, padx=(4, 0))

        self._out_dir_btn = ctk.CTkButton(
            ar, text=_('btn_output_folder'), width=82, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._open_output_folder, state="disabled",
        )
        self._out_dir_btn.grid(row=0, column=13, padx=(4, 0))

        ctk.CTkCheckBox(
            ar, text=_('chk_auto_html'), variable=self.auto_open_var,
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            width=90, checkbox_height=14, checkbox_width=14,
        ).grid(row=0, column=14, padx=(6, 0))

        mode_row = ctk.CTkFrame(card, fg_color="transparent")
        mode_row.grid(row=3, column=0, columnspan=7, padx=14, pady=(0, 10), sticky="ew")
        mode_row.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(mode_row, text=_('ux_mode_label'),
                     font=ctk.CTkFont(size=10, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._ux_mode_var = ctk.StringVar(value=_('ux_mode_basic'))
        self._ux_mode = ctk.CTkSegmentedButton(
            mode_row,
            values=[_('ux_mode_basic'), _('ux_mode_advanced')],
            variable=self._ux_mode_var,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda _: self._apply_ux_mode(),
        )
        self._ux_mode.grid(row=0, column=1, sticky="w")
        self._ux_hint = ctk.CTkLabel(mode_row,
                                     text=_('ux_mode_hint_basic'),
                                     font=ctk.CTkFont(size=10), text_color=C["muted"])
        self._ux_hint.grid(row=0, column=2, sticky="w", padx=(12, 0))

        self._apply_ux_mode()

    @staticmethod
    def _badge(parent, text: str, fg: str, bg: str, col: int) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(parent, text=text,
                           font=ctk.CTkFont(size=10, weight="bold"),
                           fg_color=bg, corner_radius=5,
                           text_color=fg, padx=8, pady=2)
        lbl.grid(row=0, column=col, padx=(0, 4))
        return lbl

    # ── Results table ─────────────────────────────────────────────────────────

    def _build_results(self) -> None:
        outer = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        outer.grid(row=2, column=0, padx=12, pady=(0, 4), sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        # Filter toolbar
        tb = ctk.CTkFrame(outer, fg_color="transparent")
        tb.grid(row=0, column=0, padx=12, pady=(10, 6), sticky="ew")
        tb.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tb, text=_('main_title_results'),
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._filter)
        ctk.CTkEntry(tb, textvariable=self._search_var,
                     placeholder_text=_('rpt_filter_ph'),
                     width=175, height=26, corner_radius=8,
                     fg_color=C["surface2"], border_color=C["border"],
                     font=ctk.CTkFont(size=11)
        ).grid(row=0, column=1, padx=(0, 8), sticky="e")

        self._sev_var = ctk.StringVar(value=_('rpt_filter_all'))
        ctk.CTkSegmentedButton(
            tb,
            values=[_('rpt_filter_all'), "ERROR", "WARNING", "INFO"],
            variable=self._sev_var,
            height=26, font=ctk.CTkFont(size=9, weight="bold"),
            command=lambda _: self._filter(),
        ).grid(row=0, column=2)

        # Table container
        tc = ctk.CTkFrame(outer, fg_color=C["surface2"], corner_radius=8)
        tc.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        tc.grid_columnconfigure(0, weight=1)
        tc.grid_rowconfigure(0, weight=1)

        cols = ("sev", "rule", "msg", "layer", "loc", "handle")
        self.tree = ttk.Treeview(tc, columns=cols, show="headings",
                                  style="DWG.Treeview", selectmode="browse")
        for col, title, w, anchor in [
            ("sev",    _('rpt_col_severity'),  100, "center"),
            ("rule",   _('rpt_col_rule'),       195, "w"),
            ("msg",    _('rpt_col_message'),    330, "w"),
            ("layer",  _('rpt_col_layer'),       115, "w"),
            ("loc",    _('rpt_col_location'), 150, "w"),
            ("handle", "Handle",       68, "center"),
        ]:
            self.tree.heading(col, text=title,
                              command=lambda c=col: self._sort(c))
            self.tree.column(col, width=w, minwidth=60, anchor=anchor)

        self.tree.tag_configure("ERROR",   foreground=C["error"])
        self.tree.tag_configure("WARNING", foreground=C["warning"])
        self.tree.tag_configure("INFO",    foreground=C["info"])
        self.tree.tag_configure("alt",     background="#1e2235")

        vsb = ctk.CTkScrollbar(tc, command=self.tree.yview)
        hsb = ctk.CTkScrollbar(tc, command=self.tree.xview, orientation="horizontal")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Context menu
        self._ctx = tk.Menu(self, tearoff=0,
                            bg=C["surface2"], fg=C["text"],
                            activebackground=C["accent"], activeforeground="white")
        self._ctx.add_command(label="📋  Copiar linha",           command=self._copy_row)
        self._ctx.add_command(label="🔍  Filtrar por esta regra", command=self._filter_by_rule)
        self._ctx.add_separator()
        self._ctx.add_command(label=_('main_ctx_clear_filter'),
                               command=lambda: (
                                   self._search_var.set(""),
                                   self._sev_var.set(_('rpt_filter_all')),
                               ))
        self.tree.bind("<Button-3>", lambda e: (
            self.tree.selection_set(self.tree.identify_row(e.y)),
            self._ctx.post(e.x_root, e.y_root),
        ))

        self._placeholder()

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        ftr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=26)
        ftr.grid(row=3, column=0, sticky="ew")
        ftr.grid_propagate(False)
        ftr.grid_columnconfigure(1, weight=1)

        self._progress = ctk.CTkProgressBar(ftr, width=140, height=5, mode="indeterminate")
        self._progress.grid(row=0, column=0, padx=(12, 8), pady=10)
        self._progress.set(0)

        self._footer_lbl = ctk.CTkLabel(
            ftr, text=_('footer_ready'),
            font=ctk.CTkFont(size=10), text_color=C["muted"],
        )
        self._footer_lbl.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(ftr, text=f"Vantara Tech · {AUTHOR} · v{VERSION}",
                     font=ctk.CTkFont(size=9), text_color=C["border"]
        ).grid(row=0, column=2, padx=12)

    # ── About ─────────────────────────────────────────────────────────────────

    def _open_about(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title(f"{_('about_title')} · {_('app_name')}")
        win.geometry("420x340")
        win.resizable(False, False)
        win.configure(fg_color=C["bg"])
        win.grab_set()

        # ícone
        ctk.CTkLabel(win, text="🏗️", font=ctk.CTkFont(size=48)
        ).pack(pady=(28, 4))

        # nome + versão
        ctk.CTkLabel(win, text=_('app_name'),
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=C["text"]
        ).pack()
        ctk.CTkLabel(win, text=_('about_version', version=VERSION),
                     font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).pack(pady=(2, 14))

        # separador
        sep = ctk.CTkFrame(win, height=1, fg_color=C["border"])
        sep.pack(fill="x", padx=36)

        # autoria
        ctk.CTkLabel(win, text=f"{_('about_dev')}  {AUTHOR}",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).pack(pady=(14, 2))
        ctk.CTkLabel(win, text=COMPANY,
                     font=ctk.CTkFont(size=11), text_color=C["accent"]
        ).pack()
        ctk.CTkLabel(win, text=EMAIL,
                     font=ctk.CTkFont(size=10), text_color=C["muted"],
                     cursor="hand2"
        ).pack(pady=(2, 14))

        # copyright
        ctk.CTkLabel(win, text=_('about_rights_reserved', year=2026, company=COMPANY),
                     font=ctk.CTkFont(size=9), text_color=C["border"]
        ).pack()

        ctk.CTkButton(
            win, text=_('about_close'), width=100, height=30, corner_radius=8,
            command=win.destroy,
        ).pack(pady=(16, 0))

    def _open_config(self) -> None:
        ConfigEditorWindow(self)

    def _load_runtime_profiles(self) -> dict:
        try:
            if self._PROFILES_FILE.exists():
                with open(self._PROFILES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logging.warning("Perfis runtime: falha ao carregar: %s", exc)
        return {}

    def _selected_profile_names(self) -> list[str]:
        names: list[str] = []
        selected = getattr(self, "_run_profile_var", None)
        if selected is not None:
            single_name = self._run_profile_var.get().strip()
            if single_name and single_name != self._BASE_PROFILE_LABEL and single_name in self._profiles_runtime:
                names.append(single_name)

        multi_var = getattr(self, "_run_profiles_multi_var", None)
        if multi_var is not None:
            for part in self._run_profiles_multi_var.get().split(","):
                name = part.strip()
                if name and name in self._profiles_runtime and name not in names:
                    names.append(name)
        return names

    def _build_checker(self, profile_names: list[str] | None) -> DXFChecker:
        base_checker = DXFChecker()
        if not profile_names:
            return base_checker
        profile_cfg_list = [self._profiles_runtime.get(name) for name in profile_names]
        profile_cfg_list = [cfg for cfg in profile_cfg_list if isinstance(cfg, dict)]
        if not profile_cfg_list:
            return base_checker
        merged = merge_profiles_into_config(base_checker.config, profile_cfg_list)
        return DXFChecker(config_data=merged)

    # ── Logic ─────────────────────────────────────────────────────────────────

    # ── ODA File Converter — detecção ─────────────────────────────────────────

    @staticmethod
    def _find_oda() -> str | None:
        """Procura o ODA File Converter em locais padrão do Windows."""
        candidates = [
            r"C:\Program Files\ODA\ODAFileConverter 25.12.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter 25.6.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter 24.12.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter 24.6.0\ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
        ]
        import glob
        for pat in [r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe"]:
            for match in glob.glob(pat):
                return match
        for c in candidates:
            if Path(c).exists():
                return c
        return None

    def _convert_dwg_to_dxf(self, dwg_path: str) -> str | None:
        """
        Converte .DWG → .DXF usando ODA File Converter.
        Retorna o caminho do .DXF gerado, ou None em caso de erro.
        """
        import subprocess, tempfile
        oda = self._find_oda()
        if not oda:
            return None

        dwg = Path(dwg_path)
        out_dir = Path(tempfile.mkdtemp(prefix="dwg_checker_"))
        try:
            # ODAFileConverter <InputDir> <OutputDir> <version> <type> <recurse> <audit>
            result = subprocess.run(
                [oda, str(dwg.parent), str(out_dir), "ACAD2018", "DXF", "0", "1"],
                capture_output=True, text=True, timeout=120,
            )
            # Se o processo falhou, capture stderr/stdout para diagnóstico
            if result.returncode != 0:
                self._last_dwg_error = (
                    f"ODA exited with code {result.returncode}. stderr: {result.stderr.strip()}\n"
                    f"stdout: {result.stdout.strip()}"
                )
                logging.error("ODA: falha na conversão: %s", self._last_dwg_error)
                return None

            # Procura o DXF gerado
            candidates = list(out_dir.glob(f"{dwg.stem}.dxf"))
            if not candidates:
                candidates = list(out_dir.rglob("*.dxf"))
            if candidates:
                return str(candidates[0])
            # Nenhum DXF gerado — registrar saída para diagnóstico
            self._last_dwg_error = (
                f"ODA finished but no DXF produced. stdout: {result.stdout.strip()} stderr: {result.stderr.strip()}"
            )
            logging.error("ODA: sem DXF gerado: %s", self._last_dwg_error)
        except Exception as exc:
            self._last_dwg_error = str(exc)
            logging.error("ODA: falha na conversão: %s", exc)
        return None

    def _browse(self) -> None:
        p = filedialog.askopenfilename(
            title=_('file_select_title'),
            filetypes=[
                (_('file_type_cad'), "*.dxf *.dwg"),
                (_('file_type_dxf'), "*.dxf"),
                (_('file_type_dwg'), "*.dwg"),
                (_('file_type_all'), "*.*"),
            ],
        )
        if p:
            self.file_var.set(p)
            self._file_entry.configure(border_color=C["accent"])
            self._status_icon.configure(text="📄")
            self._status_lbl.configure(text=_('main_status_file_selected', file=Path(p).name), text_color=C["muted"])
            self._footer_lbl.configure(text=_('main_footer_ready_for_verify', file=Path(p).name))

    def _run(self) -> None:
        self._profiles_runtime = self._load_runtime_profiles()
        if hasattr(self, "_run_profile_menu"):
            current = self._run_profile_var.get().strip()
            values = [self._BASE_PROFILE_LABEL, *sorted(self._profiles_runtime.keys())]
            self._run_profile_menu.configure(values=values)
            if current not in values:
                self._run_profile_var.set(self._BASE_PROFILE_LABEL)

        fp = self.file_var.get().strip()
        if not fp or not Path(fp).exists():
            messagebox.showwarning(_('dlg_no_file_title'),
                                   _('dlg_no_file_msg'))
            return
        ext = Path(fp).suffix.lower()

        if ext == ".dwg":
            oda = self._find_oda()
            if oda:
                # ODA instalado — converte automaticamente
                self.run_btn.configure(state="disabled", text=_('btn_converting'))
                self._set_busy_state(True)
                self._status_icon.configure(text="⏳")
                self._status_lbl.configure(
                    text=_('oda_converting', file=Path(fp).name),
                    text_color=C["muted"])
                self._progress.start()
                self._footer_lbl.configure(text=_('footer_oda_convert', file=Path(fp).name))
                profile_names = self._selected_profile_names()
                threading.Thread(target=self._worker_dwg, args=(fp, profile_names), daemon=True).start()
                return
            else:
                # ODA não instalado — instruções de instalação + conversão manual
                messagebox.showwarning(
                    _('dlg_oda_title'),
                    _('dlg_oda_msg'),
                )
                return

        if ext != ".dxf":
            messagebox.showwarning(_('dlg_invalid_fmt_title'),
                                   _('dlg_invalid_fmt_msg'))
            return

        size_mb = Path(fp).stat().st_size / (1024 * 1024)
        if size_mb > 100 and not messagebox.askyesno(
            _('dlg_large_file_title'),
            _('dlg_large_file_msg', size=size_mb),
        ):
            return
        self.run_btn.configure(state="disabled", text=_('btn_verifying'))
        self._set_busy_state(True)
        self._status_icon.configure(text="⏳")
        self._status_lbl.configure(text=_('main_status_verifying_file', file=Path(fp).name),
                                   text_color=C["muted"])
        self._progress.start()
        self._footer_lbl.configure(text=_('main_footer_verifying_file', file=Path(fp).name))
        self._ann_btn.configure(state="disabled")
        profile_names = self._selected_profile_names()
        threading.Thread(target=self._worker, args=(fp, profile_names), daemon=True).start()

    def _worker_dwg(self, dwg_fp: str, profile_names: list[str] | None = None) -> None:
        """Worker para .DWG: converte via ODA e depois processa como DXF."""
        self.after(0, self._footer_lbl.configure,
                   {"text": _('footer_oda_convert', file=Path(dwg_fp).name)})
        dxf_fp = self._convert_dwg_to_dxf(dwg_fp)
        if not dxf_fp:
            msg = _("dwg_convert_failed_msg")
            err = getattr(self, "_last_dwg_error", None)
            if err:
                msg += _('dwg_convert_details', err=str(err))
            self.after(0, self._on_error, msg)
            return
        self.after(0, self._status_lbl.configure,
                   {"text": _('main_status_verifying_converted', file=Path(dxf_fp).name),
                    "text_color": C["muted"]})
        self._worker(dxf_fp, profile_names)



    def _worker(self, fp: str, profile_names: list[str] | None = None) -> None:
        try:
            def _progress(name: str, i: int, total: int) -> None:
                self.after(0, self._update_progress, name, i, total)
            checker = self._build_checker(profile_names)
            result  = checker.check(fp, progress_cb=_progress)
            out_dir = str(Path(fp).parent)
            base    = str(Path(out_dir) / (Path(fp).stem + "_report"))
            html    = generate_html_report(result, base + ".html")
            csv_    = generate_csv_report(result,  base + ".csv")
            try:
                pdf_ = generate_pdf_report(result, base + ".pdf")
            except Exception as exc_pdf:
                logging.warning("PDF: falha ao gerar: %s", exc_pdf)
                pdf_ = None
            try:
                xlsx_ = generate_excel_report(result, base + ".xlsx")
            except Exception as exc_xlsx:
                logging.warning("XLSX: falha ao gerar: %s", exc_xlsx)
                xlsx_ = None
            _add_to_history(result, html)
            self.after(0, self._done, result, html, csv_, pdf_, xlsx_)
        except Exception as exc:
            tb = traceback.format_exc()
            logging.error("Erro ao processar '%s':\n%s", fp, tb)
            self.after(0, self._on_error, str(exc), tb)

    def _done(self, result: dict, html: str | None, csv_: str | None,
              pdf_: str | None = None, xlsx_: str | None = None) -> None:
        self._all_issues = result["issues"]
        self._html_path  = html
        self._csv_path   = csv_
        self._pdf_path   = pdf_
        self._xlsx_path  = xlsx_
        self._last_result = result

        self.run_btn.configure(state="normal", text=_('btn_verify'))
        self._set_busy_state(False)
        self._progress.stop()
        self._progress.set(0)

        if result["passed"]:
            self._status_icon.configure(text="✅")
            self._status_lbl.configure(
                text=f"{_('result_passed')} — {result['file']}", text_color=C["success"])
        else:
            self._status_icon.configure(text="❌")
            self._status_lbl.configure(
                text=f"{_('result_failed')} — {result['errors']} × {result['file']}",
                text_color=C["error"])

        self._err_b.configure(text=f"❌ {result['errors']}")
        self._warn_b.configure(text=f"⚠️ {result['warnings']}")
        self._info_b.configure(text=f"ℹ️ {result['infos']}")

        if html:
            self._html_btn.configure(state="normal")
            if self.auto_open_var.get():
                webbrowser.open(f"file:///{Path(html).resolve()}")
        if csv_:  self._csv_btn.configure(state="normal")
        if pdf_:  self._pdf_btn.configure(state="normal")
        if xlsx_: self._xlsx_btn.configure(state="normal")
        self._out_dir_btn.configure(state="normal")
        # Enable annotate button
        if Path(result["file_path"]).suffix.lower() == ".dxf":
            self._ann_btn.configure(state="normal")

        self._apply_ux_mode()

        self._search_var.set("")
        self._sev_var.set(_('rpt_filter_all'))
        self._populate(self._all_issues)
        _meta = "  ·  ".join(filter(None, [
            f"DXF {result.get('dxf_version_name', '')}" if result.get("dxf_version_name") else "",
            f"{result.get('file_size_mb', 0):.1f} MB"   if result.get("file_size_mb")  else "",
            f"{result.get('entity_count', 0):,} {_('rpt_entities')}" if result.get("entity_count") else "",
            f"{result.get('check_time', 0):.1f}s"        if result.get("check_time")    else "",
        ]))
        sha = result.get("sha256", "")
        sha_short = f"  ·  SHA-256: {sha[:16]}…" if sha else ""
        self._footer_lbl.configure(
            text=_('main_footer_completed', total=result['total_issues'], file=result['file'])
                 + (f"  ·  {_meta}" if _meta else "") + sha_short)

    def _annotate_dxf(self) -> None:
        """Gera cópia anotada do DXF com _QC_ISSUES layer."""
        result = getattr(self, "_last_result", None)
        if not result:
            messagebox.showwarning(_('annotate_title'), _('annotate_no_result'), parent=self)
            return
        fp  = result["file_path"]
        out = str(Path(fp).parent / (Path(fp).stem + "_annotated.dxf"))
        try:
            from checker.annotate import annotate_dxf
            path = annotate_dxf(result, out)
            messagebox.showinfo(_('annotate_done_title'),
                                _('annotate_done', path=path), parent=self)
            os.startfile(str(Path(path).parent))
        except Exception as exc:
            logging.error("annotate_dxf: %s", exc)
            messagebox.showerror(_('main_error_title'), _('annotate_error', err=str(exc)), parent=self)

    def _on_error(self, err: str, tb: str = "") -> None:
        self.run_btn.configure(state="normal", text=_('btn_verify'))
        self._set_busy_state(False)
        self._progress.stop()
        self._progress.set(0)
        self._status_icon.configure(text="⚠️")
        self._status_lbl.configure(text=_('main_status_error_processing'), text_color=C["error"])
        detail = _('main_error_detail_saved', log=_LOG_FILE) if tb else ""
        messagebox.showerror(_('main_error_title'), _('main_error_msg', err=err, detail=detail))

    # ── Table helpers ─────────────────────────────────────────────────────────

    def _placeholder(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end",
                         values=("—", "—", _('main_placeholder_no_file'), "—", "—", "—"))

    def _populate(self, issues: list) -> None:
        self.tree.delete(*self.tree.get_children())
        if not issues:
            self.tree.insert("", "end",
                             values=("—", "—", _('rpt_no_issues'), "—", "—", "—"))
            return
        for idx, issue in enumerate(issues):
            tags = [issue.severity.value]
            if idx % 2 == 1:
                tags.append("alt")
            self.tree.insert("", "end", values=(
                issue.severity.value,
                issue.rule,
                issue.message,
                issue.layer  or "—",
                getattr(issue, "location", "") or "—",
                issue.handle or "—",
            ), tags=tuple(tags))

    def _filter(self, *_) -> None:
        if not self._all_issues:
            return
        q   = self._search_var.get().lower()
        sev = self._sev_var.get()
        out = [
            i for i in self._all_issues
            if (sev == _('rpt_filter_all') or i.severity.value == sev)
            and (not q or any(q in str(x).lower() for x in (
                i.message, i.rule, i.layer or "",
                getattr(i, "location", "") or "",
                i.details or "",
            )))
        ]
        self._populate(out)

    def _sort(self, col: str) -> None:
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        items.sort()
        for i, (_, k) in enumerate(items):
            self.tree.move(k, "", i)

    def _copy_row(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        text = "\t".join(str(v) for v in self.tree.item(sel[0], "values"))
        self.clipboard_clear()
        self.clipboard_append(text)
        self._footer_lbl.configure(text=_('footer_row_copied'))

    def _filter_by_rule(self) -> None:
        sel = self.tree.selection()
        if sel:
            self._search_var.set(self.tree.item(sel[0], "values")[1])

    def _update_progress(self, name: str, i: int, total: int) -> None:
        label = name.replace("check_", "").replace("_", " ").title()
        self._status_lbl.configure(
            text=_('main_status_rule_progress', i=i, total=total, label=label), text_color=C["muted"])
        self._footer_lbl.configure(text=_('main_footer_rule_progress', i=i, total=total, label=label))

    # ── Drag & Drop ───────────────────────────────────────────────────────────

    def _setup_dnd(self) -> None:
        """Registra a janela principal como alvo de drag & drop."""
        if not _DND_OK:
            return
        try:
            self.drop_target_register(_tkdnd.DND_FILES)
            self.dnd_bind("<<Drop>>",      self._on_drop)
            self.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self.dnd_bind("<<DragLeave>>", self._on_drag_leave)
            # Registra também a entrada de arquivo diretamente
            self._file_entry.drop_target_register(_tkdnd.DND_FILES)
            self._file_entry.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as exc:
            logging.warning("DnD: erro ao registrar targets: %s", exc)

    def _on_drag_enter(self, event) -> None:  # noqa: ARG002
        """Feedback visual quando arquivo é arrastado sobre a janela."""
        self._file_entry.configure(border_color=C["accent"])
        self._footer_lbl.configure(text=_('dnd_drop_hint'))

    def _on_drag_leave(self, event) -> None:  # noqa: ARG002
        """Restaura visual quando arrastar sai da janela."""
        self._file_entry.configure(border_color=C["border"])
        self._footer_lbl.configure(text=_('footer_ready'))

    def _on_drop(self, event) -> None:
        """Processa arquivo DXF solto via drag & drop."""
        self._file_entry.configure(border_color=C["border"])
        data = event.data.strip()
        # tkinterdnd2 envolve caminhos com espaços em chaves: {C:/path/my file.dxf}
        if data.startswith("{") and "}" in data:
            fp = data[1 : data.index("}")]
        else:
            fp = data.split()[0]

        if not Path(fp).exists():
            messagebox.showwarning(
                _('compare_not_found'), _('dnd_not_found_msg', path=fp), parent=self)
            self._footer_lbl.configure(text=_('footer_ready'))
            return

        ext = Path(fp).suffix.lower()
        if ext not in (".dxf", ".dwg"):
            messagebox.showwarning(
                _('dlg_invalid_fmt_title'),
                _('dnd_invalid_drop_msg'),
                parent=self,
            )
            self._footer_lbl.configure(text=_('footer_ready'))
            return

        self.file_var.set(fp)
        self._file_entry.configure(border_color=C["accent"])
        self._footer_lbl.configure(text=_('dnd_file_loaded', file=Path(fp).name))

    # ── Atalhos de teclado ────────────────────────────────────────────────────

    def _setup_shortcuts(self) -> None:
        """Registra atalhos de teclado globais."""
        self.bind("<F5>",        lambda e: self._run())
        self.bind("<Control-o>", lambda e: self._browse())
        self.bind("<Control-O>", lambda e: self._browse())
        self.bind("<Control-h>", lambda e: self._open_history())
        self.bind("<Control-H>", lambda e: self._open_history())
        self.bind("<Control-l>", lambda e: self._open_batch())
        self.bind("<Control-L>", lambda e: self._open_batch())
        self.bind("<Control-w>", lambda e: self._open_watch())
        self.bind("<Control-W>", lambda e: self._open_watch())
        self.bind("<Control-d>", lambda e: self._open_compare())
        self.bind("<Control-D>", lambda e: self._open_compare())

    def _open_batch(self) -> None:
        BatchWindow(self)

    def _open_watch(self) -> None:
        WatchFolderWindow(self)

    def _open_compare(self) -> None:
        CompareWindow(self)

    def _on_update_result(self, info: dict | None) -> None:
        """Chamado após a verificação de auto-update (thread-safe via after())."""
        if info:
            self._show_update_banner(info["version"], info["url"])

    def _show_update_banner(self, latest: str, url: str) -> None:
        """Exibe faixa discreta de atualização disponível no topo da janela."""
        banner = ctk.CTkFrame(self, fg_color="#1a2e1a", corner_radius=0, height=30)
        # Insere acima do header (row -1 não funciona em grid; usamos place)
        banner.place(relx=0, rely=0, relwidth=1, height=30)

        ctk.CTkLabel(
            banner,
            text=_('update_banner', latest=latest),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C["success"],
            cursor="hand2",
        ).place(relx=0.5, rely=0.5, anchor="center")

        banner.bind("<Button-1>", lambda _: webbrowser.open(url))
        for w in banner.winfo_children():
            w.bind("<Button-1>", lambda _: webbrowser.open(url))

        # Fecha o banner ao clicar no X interno
        close_btn = ctk.CTkButton(
            banner, text="✕", width=22, height=22, corner_radius=4,
            fg_color="transparent", hover_color="#2a3e2a",
            font=ctk.CTkFont(size=9), text_color=C["muted"],
            command=banner.destroy,
        )
        close_btn.place(relx=1.0, rely=0.5, anchor="e", x=-8)

    def _open_html(self) -> None:
        if self._html_path and Path(self._html_path).exists():
            webbrowser.open(f"file:///{Path(self._html_path).resolve()}")

    def _open_csv(self) -> None:
        if self._csv_path and Path(self._csv_path).exists():
            os.startfile(str(Path(self._csv_path).resolve()))

    def _open_pdf(self) -> None:
        if self._pdf_path and Path(self._pdf_path).exists():
            os.startfile(str(Path(self._pdf_path).resolve()))

    def _open_xlsx(self) -> None:
        if self._xlsx_path and Path(self._xlsx_path).exists():
            os.startfile(str(Path(self._xlsx_path).resolve()))

    def _open_output_folder(self) -> None:
        result = getattr(self, "_last_result", None)
        if not result:
            return
        try:
            os.startfile(str(Path(result["file_path"]).resolve().parent))
        except Exception:
            pass

    def _clear_selection(self) -> None:
        self.file_var.set("")
        self._file_entry.configure(border_color=C["border"])
        self._status_icon.configure(text="⏳")
        self._status_lbl.configure(text=_('main_status_waiting'), text_color=C["muted"])
        self._footer_lbl.configure(text=_('footer_ready'))
        self._html_btn.configure(state="disabled")
        self._csv_btn.configure(state="disabled")
        self._pdf_btn.configure(state="disabled")
        self._xlsx_btn.configure(state="disabled")
        self._ann_btn.configure(state="disabled")
        self._out_dir_btn.configure(state="disabled")
        self._all_issues = []
        self._placeholder()
        self._apply_ux_mode()

    def _set_busy_state(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for btn in [
            getattr(self, "_btn_open", None),
            getattr(self, "_btn_batch", None),
            getattr(self, "_btn_clear", None),
            getattr(self, "_btn_history", None),
            getattr(self, "_btn_watch", None),
            getattr(self, "_btn_compare", None),
            getattr(self, "_btn_config", None),
            getattr(self, "_btn_about", None),
            getattr(self, "_btn_diag", None),
        ]:
            if btn is not None:
                btn.configure(state=state)

    def _open_history(self) -> None:
        HistoryWindow(self)

    def _apply_ux_mode(self) -> None:
        mode = getattr(self, "_ux_mode_var", None)
        mode_val = mode.get() if mode is not None else _('ux_mode_basic')
        advanced = (mode_val == _('ux_mode_advanced'))

        if not advanced:
            self.strict_var.set(False)

        self._strict_chk.configure(state="normal" if advanced else "disabled")
        self._csv_btn.configure(state=("normal" if (advanced and self._csv_path) else "disabled"))
        self._pdf_btn.configure(state=("normal" if (advanced and self._pdf_path) else "disabled"))
        self._xlsx_btn.configure(state=("normal" if (advanced and self._xlsx_path) else "disabled"))
        self._ann_btn.configure(state=("normal" if (advanced and getattr(self, "_last_result", None)) else "disabled"))
        self._out_dir_btn.configure(state=("normal" if (advanced and getattr(self, "_last_result", None)) else "disabled"))
        self._ux_hint.configure(
            text=(
                _('ux_mode_hint_basic')
                if not advanced else
                _('ux_mode_hint_advanced')
            )
        )

    def _collect_diagnostics(self) -> dict:
        cfg_path = _BASE_DIR / "config.yaml"
        oda = self._find_oda()
        template_dir = _BASE_DIR / "templates"
        di = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "app_version": VERSION,
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "base_dir": str(_BASE_DIR.resolve()),
            "cwd": str(Path.cwd().resolve()),
            "config_path": str(cfg_path.resolve()),
            "config_exists": cfg_path.exists(),
            "log_path": str(_LOG_FILE.resolve()),
            "log_exists": _LOG_FILE.exists(),
            "templates_dir": str(template_dir.resolve()),
            "templates_exists": template_dir.exists(),
            "oda_found": bool(oda),
            "oda_path": oda or "",
            "dnd_enabled": bool(_DND_OK),
        }
        return di

    def _open_diagnostics(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title(_('diag_title'))
        win.geometry("760x500")
        win.minsize(680, 420)
        win.configure(fg_color=C["bg"])
        win.grab_set()

        root = ctk.CTkFrame(win, fg_color=C["surface"], corner_radius=10)
        root.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(root, text=_('diag_header'),
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=C["text"]
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(root,
                 text=_('diag_desc'),
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).pack(anchor="w", padx=12, pady=(0, 8))

        box = ctk.CTkTextbox(root, fg_color=C["surface2"], border_color=C["border"], border_width=1)
        box.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        def _render() -> None:
            d = self._collect_diagnostics()
            lines = [
                f"timestamp: {d['timestamp']}",
                f"app_version: {d['app_version']}",
                f"python_version: {d['python_version']}",
                f"python_executable: {d['python_executable']}",
                f"platform: {d['platform']}",
                f"base_dir: {d['base_dir']}",
                f"cwd: {d['cwd']}",
                f"config_path: {d['config_path']}",
                f"config_exists: {d['config_exists']}",
                f"templates_dir: {d['templates_dir']}",
                f"templates_exists: {d['templates_exists']}",
                f"log_path: {d['log_path']}",
                f"log_exists: {d['log_exists']}",
                f"oda_found: {d['oda_found']}",
                f"oda_path: {d['oda_path']}",
                f"dnd_enabled: {d['dnd_enabled']}",
            ]
            txt = "\n".join(lines)
            box.delete("1.0", "end")
            box.insert("1.0", txt)

        def _copy() -> None:
            self.clipboard_clear()
            self.clipboard_append(box.get("1.0", "end").strip())
            self._footer_lbl.configure(text=_('footer_diag_copied'))

        def _save() -> None:
            p = filedialog.asksaveasfilename(
                title=_('diag_save_title'),
                defaultextension=".txt",
                filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
                initialfile=f"{_('diag_save_filename')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            )
            if not p:
                return
            try:
                Path(p).write_text(box.get("1.0", "end").strip(), encoding="utf-8")
                self._footer_lbl.configure(text=_('footer_diag_saved', name=Path(p).name))
            except Exception as exc:
                messagebox.showerror(_('diag_save_error_title'), _('diag_save_error_msg', err=str(exc)), parent=win)

        actions = ctk.CTkFrame(root, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(actions, text=_('diag_btn_refresh'), width=96, height=28, command=_render).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text=_('diag_btn_copy'), width=86, height=28,
                      fg_color=C["surface2"], hover_color=C["border"], command=_copy).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text=_('diag_btn_save'), width=86, height=28,
                      fg_color=C["surface2"], hover_color=C["border"], command=_save).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text=_('diag_btn_close'), width=86, height=28,
                      fg_color=C["surface2"], hover_color=C["border"], command=win.destroy).pack(side="right")

        _render()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--cli" in sys.argv:
        sys.argv.remove("--cli")
        from checker.cli import main as _cli_main
        _cli_main()
    else:
        set_lang(get_lang())
        app = App()
        app.mainloop()
