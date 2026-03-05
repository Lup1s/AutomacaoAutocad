"""
DWG Quality Checker — Launcher Minimalista v2.1
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from checker.core import DXFChecker
from checker.report import generate_csv_report, generate_html_report

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = "2.1.0"
AUTHOR  = "Luiz Q. Melo"
COMPANY = "Vantara Tech"
EMAIL   = "luiz.queiroz240202@gmail.com"

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
        self.title("Histórico de Verificações")
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
        ctk.CTkLabel(tb, text="📜  Histórico",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(tb, text="🗑️  Limpar", width=90, height=26, corner_radius=8,
                      fg_color=C["surface2"], hover_color=C["border"],
                      font=ctk.CTkFont(size=11), command=self._clear
        ).grid(row=0, column=2)

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
            ("ts",       "Data/Hora",  145), ("file",     "Arquivo",  255),
            ("status",   "Status",      82), ("errors",   "Erros",     58),
            ("warnings", "Avisos",      60), ("infos",    "Infos",     52),
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

        ctk.CTkLabel(self, text="Duplo clique para abrir o relatório HTML",
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=2, column=0, pady=(0, 8))

        self._refresh()

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._html_map.clear()
        for idx, e in enumerate(_load_history()):
            tag  = "pass" if e["passed"] else "fail"
            tags = (tag, "alt") if idx % 2 else (tag,)
            iid  = str(idx)
            self.tree.insert("", "end", iid=iid, values=(
                e["timestamp"], e["file"],
                "✅ OK" if e["passed"] else "❌ FALHOU",
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
            messagebox.showinfo("Não encontrado", "Relatório não encontrado.", parent=self)

    def _clear(self) -> None:
        if messagebox.askyesno("Limpar histórico", "Apagar todo o histórico?", parent=self):
            _save_history([])
            self._refresh()


# ── Batch Verification Window ─────────────────────────────────────────────────

class BatchWindow(ctk.CTkToplevel):
    """Verifica todos os arquivos DXF de uma pasta em lote."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("Verificação em Lote")
        self.geometry("760x540")
        self.configure(fg_color=C["bg"])
        self.resizable(True, True)
        self._files: list[str] = []
        self._html_map: dict[str, str | None] = {}
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

        ctk.CTkLabel(fc, text="Pasta:",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=0, padx=(14, 8), pady=10, sticky="w")

        self._folder_var = ctk.StringVar()
        ctk.CTkEntry(fc, textvariable=self._folder_var,
                     placeholder_text="Selecione uma pasta com arquivos DXF...",
                     height=30, corner_radius=8,
                     fg_color=C["surface2"], border_color=C["border"],
                     font=ctk.CTkFont(size=11)
        ).grid(row=0, column=1, padx=(0, 8), pady=10, sticky="ew")

        ctk.CTkButton(fc, text="📂 Abrir", width=82, height=30, corner_radius=8,
                      command=self._browse_folder
        ).grid(row=0, column=2, padx=(0, 12), pady=10)

        # ── Action row ────────────────────────────────────────────────────────
        ar = ctk.CTkFrame(self, fg_color="transparent")
        ar.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")
        ar.grid_columnconfigure(2, weight=1)

        self._start_btn = ctk.CTkButton(
            ar, text="🔍  Iniciar Lote", width=130, height=30, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._start,
        )
        self._start_btn.grid(row=0, column=0, padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            ar, text="⏹ Parar", width=80, height=30, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), state="disabled", command=self._stop_batch,
        )
        self._stop_btn.grid(row=0, column=1, padx=(0, 12))

        self._batch_lbl = ctk.CTkLabel(
            ar, text="Selecione uma pasta e clique em Iniciar Lote.",
            font=ctk.CTkFont(size=11), text_color=C["muted"],
        )
        self._batch_lbl.grid(row=0, column=2, sticky="w")

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
            ("file",     "Arquivo",  310, "w"),
            ("status",   "Status",    90, "center"),
            ("errors",   "Erros",     60, "center"),
            ("warnings", "Avisos",    60, "center"),
            ("infos",    "Infos",     55, "center"),
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

        ctk.CTkLabel(self, text="Duplo clique para abrir o relatório HTML",
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
        d = filedialog.askdirectory(title="Selecionar pasta com arquivos DXF")
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
                               values=(Path(f).name, "⏳ Aguardando", "—", "—", "—"),
                               tags=tags)
        n = len(self._files)
        self._batch_lbl.configure(text=f"{n} arquivo(s) DXF encontrado(s) — clique em Iniciar Lote")

    def _start(self) -> None:
        if not self._files:
            folder = self._folder_var.get().strip()
            if folder and Path(folder).exists():
                self._scan_folder(folder)
            if not self._files:
                messagebox.showwarning("Sem arquivos",
                                       "Nenhum arquivo DXF encontrado na pasta.", parent=self)
                return
        self._running    = True
        self._stop_flag  = False
        self._batch_prog.set(0)
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        threading.Thread(target=self._batch_worker, daemon=True).start()

    def _stop_batch(self) -> None:
        self._stop_flag = True
        self._batch_lbl.configure(text="Parando após o arquivo atual...")

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
        vals[1] = "⏳ Verificando..."
        self._tree.item(iid, values=vals)

    def _set_done(self, iid: str, result: dict, html: str | None) -> None:
        tag  = "pass" if result["passed"] else "fail"
        base = ("alt",) if int(iid) % 2 else ()
        self._html_map[iid] = html
        self._tree.item(iid, tags=(tag,) + base, values=(
            Path(result["file_path"]).name,
            "✅ OK" if result["passed"] else "❌ FALHOU",
            result["errors"], result["warnings"], result["infos"],
        ))

    def _set_err(self, iid: str, msg: str) -> None:
        base = ("alt",) if int(iid) % 2 else ()
        self._tree.item(iid, tags=("err",) + base)
        vals = list(self._tree.item(iid, "values"))
        vals[1] = f"⚠️ ERRO"
        self._tree.item(iid, values=vals)

    def _update_progress(self, done: int, total: int) -> None:
        self._batch_prog.set(done / total)
        self._prog_lbl.configure(text=f"{done} / {total} arquivos")
        self._batch_lbl.configure(text=f"Processando: {done}/{total}  ·  aguarde...")

    def _batch_finished(self) -> None:
        self._running = False
        passed = sum(1 for v in self._html_map.values() if v)
        total  = len(self._files)
        if self._stop_flag:
            self._batch_lbl.configure(text=f"Lote interrompido — {passed} relatório(s) gerado(s)")
        else:
            self._batch_lbl.configure(
                text=f"✅ Lote concluído — {passed}/{total} relatório(s) gerado(s)")
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    def _open_report(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        html = self._html_map.get(sel[0])
        if html and Path(html).exists():
            webbrowser.open(f"file:///{Path(html).resolve()}")
        else:
            messagebox.showinfo("Não encontrado", "Relatório não encontrado.", parent=self)


# ── Config Editor Window ──────────────────────────────────────────────────────

class ConfigEditorWindow(ctk.CTkToplevel):
    """Editor visual para config.yaml — sem precisar editar o arquivo manualmente."""

    _CONFIG_FILE = _BASE_DIR / "config.yaml"

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("⚙️  Editor de Configurações")
        self.geometry("600x640")
        self.minsize(560, 580)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self._cfg = self._load()
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

    def _save(self) -> None:
        try:
            self._collect()
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.dump(self._cfg, f, allow_unicode=True,
                          default_flow_style=False, sort_keys=False)
            messagebox.showinfo("Salvo", "✅ Configurações salvas com sucesso!", parent=self)
            self.destroy()
        except Exception as exc:
            logging.error("ConfigEditor: erro ao salvar: %s", exc)
            messagebox.showerror("Erro", f"Não foi possível salvar:\n{exc}", parent=self)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=48)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="⚙️", font=ctk.CTkFont(size=22)
        ).grid(row=0, column=0, padx=(16, 8), pady=8)
        ctk.CTkLabel(hdr, text="Editor de Configurações",
                     font=ctk.CTkFont(size=14, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(hdr, text="config.yaml",
                     font=ctk.CTkFont(size=10), text_color=C["muted"]
        ).grid(row=0, column=2, padx=14)

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
        tabs.grid(row=1, column=0, padx=12, pady=(8, 4), sticky="nsew")
        tabs.add("📐  Camadas")
        tabs.add("✏️  Textos")
        tabs.add("🔲  Desenho")
        self._build_layers_tab(tabs.tab("📐  Camadas"))
        self._build_text_tab(tabs.tab("✏️  Textos"))
        self._build_drawing_tab(tabs.tab("🔲  Desenho"))

        # ── Footer ────────────────────────────────────────────────────────────
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.grid(row=2, column=0, padx=14, pady=(4, 14), sticky="ew")
        ftr.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            ftr, text="💾  Salvar", width=120, height=36, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._save,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            ftr, text="Cancelar", width=95, height=36, corner_radius=8,
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
        ctk.CTkLabel(parent, text="Layers obrigatórias",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, sticky="w", pady=(12, 2))
        ctk.CTkLabel(parent,
                     text="O desenho DEVE conter todas estas layers (vazio = não verificar)",
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
            placeholder_text="Nome da layer (ex: TEXTO, COTA)...",
            height=30, corner_radius=6, font=ctk.CTkFont(size=11),
            fg_color=C["surface"], border_color=C["border"],
        )
        new_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        new_entry.bind("<Return>", lambda _: self._add_layer())

        ctk.CTkButton(add_row, text="＋ Adicionar", width=100, height=30,
                      corner_radius=6, font=ctk.CTkFont(size=11),
                      command=self._add_layer,
        ).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(add_row, text="🗑 Remover", width=90, height=30,
                      corner_radius=6, font=ctk.CTkFont(size=11),
                      fg_color=C["surface"], hover_color=C["border"],
                      text_color=C["muted"], command=self._remove_layer,
        ).grid(row=0, column=2)

        # --- Naming convention ---
        ctk.CTkLabel(parent, text="Padrão de nomenclatura (Regex)",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=3, column=0, sticky="w", pady=(12, 2))
        ctk.CTkLabel(parent,
                     text='Ex: "^[A-Z]{2,4}-[A-Z0-9_-]+$"  →  ARQ-PAREDE, EST-VIGA\n'
                          '(vazio = desabilitar verificação de nomenclatura)',
                     font=ctk.CTkFont(size=10), text_color=C["muted"], justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(0, 6))

        self._naming_var = ctk.StringVar(
            value=layers_cfg.get("naming_convention") or "")
        ctk.CTkEntry(parent, textvariable=self._naming_var,
                     placeholder_text="Regex (vazio = desabilitado)...",
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

        ctk.CTkLabel(parent, text="Alturas de texto permitidas",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(12, 8))

        # --- Reference table ---
        ref = ctk.CTkFrame(parent, fg_color=C["surface2"], corner_radius=8)
        ref.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 20))

        headers = [("Tipo de projeto", 230), ("Mín", 70), ("Máx", 70)]
        for col, (h, w) in enumerate(headers):
            ctk.CTkLabel(ref, text=h, font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=C["muted"], width=w, anchor="w"
            ).grid(row=0, column=col, padx=(10, 4), pady=(6, 2), sticky="w")

        for i, (tipo, mn, mx) in enumerate([
            ("Topografia / UTM (m)",          "0.50", "20.0"),
            ("Arquitetura 1:50 (mm)",          "1.50", "10.0"),
            ("Estrutural / Civil (m)",         "0.10",  "5.0"),
            ("Mecânico / Industrial (mm)",    "2.00", "15.0"),
            ("Levantamento topográfico (m)",  "0.03", "50.0"),
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
            ("Altura mínima", "min_height", "_min_h_var", C["success"]),
            ("Altura máxima", "max_height", "_max_h_var", C["error"]),
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
                     text="Unidades devem ser consistentes com o arquivo DXF (metros, mm, etc.)",
                     font=ctk.CTkFont(size=10), text_color=C["muted"],
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(12, 0))

    # ── Tab: Desenho ──────────────────────────────────────────────────────────

    def _build_drawing_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        drawing_cfg = self._cfg.get("drawing", {})
        self._drawing_vars: dict[str, ctk.BooleanVar] = {}

        RULES = [
            ("check_entities_on_layer_0",
             "Entidades na Layer 0",
             "Objetos desenhados diretamente na layer 0 (má prática de organização)"),
            ("check_unused_blocks",
             "Blocos não utilizados",
             "Blocos definidos no arquivo mas nunca inseridos no model space"),
            ("check_empty_layers",
             "Layers vazias",
             "Layers existentes sem nenhuma entidade associada"),
            ("check_frozen_layers",
             "Layers congeladas com dados",
             "Layers congeladas que ainda possuem entidades (potencial confusão)"),
            ("check_off_layers",
             "Layers desligadas com dados",
             "Layers desligadas (off) que ainda possuem entidades"),
            ("check_color_bylayer",
             "Cor explícita (não ByLayer)",
             "Entidades com cor definida diretamente, fora do padrão ByLayer"),
            ("check_linetype_bylayer",
             "Tipo de linha explícito",
             "Entidades com tipo de linha definido diretamente, fora do padrão ByLayer"),
            ("check_duplicates",
             "Entidades duplicadas",
             "Detecta entidades sobrepostas com mesmo tipo, layer e coordenadas"),
            ("check_xrefs",
             "Referências externas (XREF)",
             "Verifica se XREFs estão carregadas e acessíveis no disco"),
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


# ── Main Application ──────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"DWG Quality Checker  v{VERSION}")
        self.geometry("1020x680")
        self.minsize(800, 560)
        self.configure(fg_color=C["bg"])

        self._html_path:  str | None = None
        self._csv_path:   str | None = None
        self._all_issues: list       = []
        self.auto_open_var = ctk.BooleanVar(value=True)

        _apply_style()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_controls()
        self._build_results()
        self._build_footer()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        h = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0, height=50)
        h.grid(row=0, column=0, sticky="ew")
        h.grid_propagate(False)
        h.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(h, text="🏗️", font=ctk.CTkFont(size=22)
        ).grid(row=0, column=0, padx=(18, 8), pady=8)

        ctk.CTkLabel(h, text="DWG Quality Checker",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=1, sticky="w")

        ctk.CTkButton(
            h, text="📜  Histórico", width=105, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_history,
        ).grid(row=0, column=2, padx=(0, 6))

        ctk.CTkButton(
            h, text="⚙️  Config", width=90, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_config,
        ).grid(row=0, column=3, padx=(0, 6))

        ctk.CTkButton(
            h, text="ℹ️  Sobre", width=85, height=28, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11), text_color=C["muted"],
            command=self._open_about,
        ).grid(row=0, column=4, padx=(0, 14))

    # ── Controls ──────────────────────────────────────────────────────────────

    def _build_controls(self) -> None:
        card = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        card.grid(row=1, column=0, padx=12, pady=(8, 4), sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # ── Row 0: file picker ────────────────────────────────────────────────
        ctk.CTkLabel(card, text="Arquivo:",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=C["muted"]
        ).grid(row=0, column=0, padx=(14, 8), pady=(12, 6), sticky="w")

        fr = ctk.CTkFrame(card, fg_color="transparent")
        fr.grid(row=0, column=1, columnspan=6, padx=(0, 14), pady=(12, 6), sticky="ew")
        fr.grid_columnconfigure(0, weight=1)

        self.file_var = ctk.StringVar()
        self._file_entry = ctk.CTkEntry(
            fr, textvariable=self.file_var,
            placeholder_text="Selecione um arquivo .DXF  (suporte a .DWG em breve)...",
            height=32, corner_radius=8,
            fg_color=C["surface2"], border_color=C["border"],
            font=ctk.CTkFont(size=11),
        )
        self._file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            fr, text="📂  Abrir", width=90, height=32, corner_radius=8,
            command=self._browse,
        ).grid(row=0, column=1, padx=(0, 4))
        ctk.CTkButton(
            fr, text="📁 Pasta", width=80, height=32, corner_radius=8,
            fg_color=C["surface2"], hover_color=C["border"],
            font=ctk.CTkFont(size=11),
            command=self._open_batch,
        ).grid(row=0, column=2)

        # ── Row 1: action ─────────────────────────────────────────────────────
        ar = ctk.CTkFrame(card, fg_color="transparent")
        ar.grid(row=1, column=0, columnspan=7, padx=14, pady=(0, 12), sticky="ew")
        ar.grid_columnconfigure(3, weight=1)

        self.run_btn = ctk.CTkButton(
            ar, text="🔍  Verificar",
            width=125, height=32, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._run,
        )
        self.run_btn.grid(row=0, column=0, padx=(0, 12))

        self.strict_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(ar, text="Strict", variable=self.strict_var,
                        font=ctk.CTkFont(size=11), text_color=C["muted"], width=68
        ).grid(row=0, column=1, padx=(0, 20))

        self._status_icon = ctk.CTkLabel(ar, text="⏳", font=ctk.CTkFont(size=15))
        self._status_icon.grid(row=0, column=2, padx=(0, 5))

        self._status_lbl = ctk.CTkLabel(
            ar, text="Aguardando arquivo...",
            font=ctk.CTkFont(size=11), text_color=C["muted"],
        )
        self._status_lbl.grid(row=0, column=3, sticky="w")

        # Badges
        bg = ctk.CTkFrame(ar, fg_color="transparent")
        bg.grid(row=0, column=4, padx=(0, 10))
        self._err_b  = self._badge(bg, "❌ 0", C["error"],   C["err_bg"],  0)
        self._warn_b = self._badge(bg, "⚠️ 0", C["warning"], C["warn_bg"], 1)
        self._info_b = self._badge(bg, "ℹ️ 0", C["info"],    C["info_bg"], 2)

        # Report buttons
        self._html_btn = ctk.CTkButton(
            ar, text="📄 HTML", width=76, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._open_html, state="disabled",
        )
        self._html_btn.grid(row=0, column=5, padx=(0, 4))

        self._csv_btn = ctk.CTkButton(
            ar, text="📊 CSV", width=64, height=26, corner_radius=8,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=C["surface2"], hover_color=C["border"],
            command=self._open_csv, state="disabled",
        )
        self._csv_btn.grid(row=0, column=6)

        ctk.CTkCheckBox(
            ar, text="Auto HTML", variable=self.auto_open_var,
            font=ctk.CTkFont(size=10), text_color=C["muted"],
            width=90, checkbox_height=14, checkbox_width=14,
        ).grid(row=0, column=7, padx=(6, 0))

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

        ctk.CTkLabel(tb, text="Resultados",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._filter)
        ctk.CTkEntry(tb, textvariable=self._search_var,
                     placeholder_text="🔎  Filtrar...",
                     width=175, height=26, corner_radius=8,
                     fg_color=C["surface2"], border_color=C["border"],
                     font=ctk.CTkFont(size=11)
        ).grid(row=0, column=1, padx=(0, 8), sticky="e")

        self._sev_var = ctk.StringVar(value="Todos")
        ctk.CTkSegmentedButton(
            tb,
            values=["Todos", "ERROR", "WARNING", "INFO"],
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
            ("sev",    "Severidade",  100, "center"),
            ("rule",   "Regra",       195, "w"),
            ("msg",    "Mensagem",    330, "w"),
            ("layer",  "Layer",       115, "w"),
            ("loc",    "Localização", 150, "w"),
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
        self._ctx.add_command(label="🗑️   Limpar filtro",
                               command=lambda: (
                                   self._search_var.set(""),
                                   self._sev_var.set("Todos"),
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
            ftr, text="Pronto.",
            font=ctk.CTkFont(size=10), text_color=C["muted"],
        )
        self._footer_lbl.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(ftr, text=f"Vantara Tech · {AUTHOR} · v{VERSION}",
                     font=ctk.CTkFont(size=9), text_color=C["border"]
        ).grid(row=0, column=2, padx=12)

    # ── About ─────────────────────────────────────────────────────────────────

    def _open_about(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("Sobre o DWG Quality Checker")
        win.geometry("420x340")
        win.resizable(False, False)
        win.configure(fg_color=C["bg"])
        win.grab_set()

        # ícone
        ctk.CTkLabel(win, text="🏗️", font=ctk.CTkFont(size=48)
        ).pack(pady=(28, 4))

        # nome + versão
        ctk.CTkLabel(win, text="DWG Quality Checker",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=C["text"]
        ).pack()
        ctk.CTkLabel(win, text=f"Versão {VERSION}",
                     font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).pack(pady=(2, 14))

        # separador
        sep = ctk.CTkFrame(win, height=1, fg_color=C["border"])
        sep.pack(fill="x", padx=36)

        # autoria
        ctk.CTkLabel(win, text=f"Desenvolvido por  {AUTHOR}",
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
        ctk.CTkLabel(win, text=f"© 2026 {COMPANY}. Todos os direitos reservados.",
                     font=ctk.CTkFont(size=9), text_color=C["border"]
        ).pack()

        ctk.CTkButton(
            win, text="Fechar", width=100, height=30, corner_radius=8,
            command=win.destroy,
        ).pack(pady=(16, 0))

    def _open_config(self) -> None:
        ConfigEditorWindow(self)

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        p = filedialog.askopenfilename(
            title="Selecionar arquivo DXF",
            filetypes=[("DXF — Drawing Exchange Format", "*.dxf"), ("Todos os arquivos", "*.*")],
        )
        if p:
            self.file_var.set(p)
            self._file_entry.configure(border_color=C["accent"])

    def _run(self) -> None:
        fp = self.file_var.get().strip()
        if not fp or not Path(fp).exists():
            messagebox.showwarning("Arquivo não selecionado",
                                   "Selecione um arquivo .DXF válido.")
            return
        ext = Path(fp).suffix.lower()
        if ext == ".dwg":
            messagebox.showwarning(
                ".DWG ainda não suportado",
                "Arquivos .DWG ainda não são suportados nesta versão.\n\n"
                "Converta o arquivo para .DXF no AutoCAD:\n"
                "  Arquivo → Salvar Como → formato AutoCAD DXF (*.dxf)\n\n"
                "O suporte a .DWG estará disponível em uma versão futura."
            )
            return
        if ext != ".dxf":
            messagebox.showwarning("Formato inválido",
                                   "Apenas arquivos .DXF são suportados nesta versão.")
            return
        size_mb = Path(fp).stat().st_size / (1024 * 1024)
        if size_mb > 100 and not messagebox.askyesno(
            "Arquivo grande",
            f"O arquivo tem {size_mb:.0f} MB.\n"
            f"A verificação pode levar vários minutos.\n\nContinuar?",
        ):
            return
        self.run_btn.configure(state="disabled", text="⏳  Verificando...")
        self._status_icon.configure(text="⏳")
        self._status_lbl.configure(text=f"Verificando {Path(fp).name}...",
                                   text_color=C["muted"])
        self._progress.start()
        self._footer_lbl.configure(text=f"Verificando: {Path(fp).name}...")
        threading.Thread(target=self._worker, args=(fp,), daemon=True).start()

    def _worker(self, fp: str) -> None:
        try:
            def _progress(name: str, i: int, total: int) -> None:
                self.after(0, self._update_progress, name, i, total)
            result  = DXFChecker().check(fp, progress_cb=_progress)
            out_dir = str(Path(fp).parent)
            base    = str(Path(out_dir) / (Path(fp).stem + "_report"))
            html    = generate_html_report(result, base + ".html")
            csv_    = generate_csv_report(result,  base + ".csv")
            _add_to_history(result, html)
            self.after(0, self._done, result, html, csv_)
        except Exception as exc:
            tb = traceback.format_exc()
            logging.error("Erro ao processar '%s':\n%s", fp, tb)
            self.after(0, self._on_error, str(exc), tb)

    def _done(self, result: dict, html: str | None, csv_: str | None) -> None:
        self._all_issues = result["issues"]
        self._html_path  = html
        self._csv_path   = csv_

        self.run_btn.configure(state="normal", text="🔍  Verificar")
        self._progress.stop()
        self._progress.set(0)

        if result["passed"]:
            self._status_icon.configure(text="✅")
            self._status_lbl.configure(
                text=f"Aprovado — {result['file']}", text_color=C["success"])
        else:
            self._status_icon.configure(text="❌")
            self._status_lbl.configure(
                text=f"Reprovado — {result['errors']} erro(s) em {result['file']}",
                text_color=C["error"])

        self._err_b.configure(text=f"❌ {result['errors']}")
        self._warn_b.configure(text=f"⚠️ {result['warnings']}")
        self._info_b.configure(text=f"ℹ️ {result['infos']}")

        if html:
            self._html_btn.configure(state="normal")
            if self.auto_open_var.get():
                webbrowser.open(f"file:///{Path(html).resolve()}")
        if csv_: self._csv_btn.configure(state="normal")

        self._search_var.set("")
        self._sev_var.set("Todos")
        self._populate(self._all_issues)
        _meta = "  ·  ".join(filter(None, [
            f"DXF {result.get('dxf_version_name', '')}" if result.get("dxf_version_name") else "",
            f"{result.get('file_size_mb', 0):.1f} MB"   if result.get("file_size_mb")  else "",
            f"{result.get('entity_count', 0):,} entidades" if result.get("entity_count") else "",
            f"{result.get('check_time', 0):.1f}s"        if result.get("check_time")    else "",
        ]))
        self._footer_lbl.configure(
            text=f"Concluído — {result['total_issues']} ocorrência(s)  ·  {result['file']}"
                 + (f"  ·  {_meta}" if _meta else ""))

    def _on_error(self, err: str, tb: str = "") -> None:
        self.run_btn.configure(state="normal", text="🔍  Verificar")
        self._progress.stop()
        self._progress.set(0)
        self._status_icon.configure(text="⚠️")
        self._status_lbl.configure(text="Erro ao processar", text_color=C["error"])
        detail = f"\n\nDetalhes salvos em:\n{_LOG_FILE}" if tb else ""
        messagebox.showerror("Erro", f"Não foi possível processar o arquivo:\n\n{err}{detail}")

    # ── Table helpers ─────────────────────────────────────────────────────────

    def _placeholder(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree.insert("", "end",
                         values=("—", "—", "Nenhum arquivo verificado ainda", "—", "—", "—"))

    def _populate(self, issues: list) -> None:
        self.tree.delete(*self.tree.get_children())
        if not issues:
            self.tree.insert("", "end",
                             values=("—", "—", "🎉  Nenhum problema encontrado!", "—", "—", "—"))
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
            if (sev == "Todos" or i.severity.value == sev)
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
        self._footer_lbl.configure(text="✅ Linha copiada para a área de transferência")

    def _filter_by_rule(self) -> None:
        sel = self.tree.selection()
        if sel:
            self._search_var.set(self.tree.item(sel[0], "values")[1])

    def _update_progress(self, name: str, i: int, total: int) -> None:
        label = name.replace("check_", "").replace("_", " ").title()
        self._status_lbl.configure(
            text=f"[{i}/{total}] {label}...", text_color=C["muted"])
        self._footer_lbl.configure(text=f"Regra {i}/{total}: {label}")

    def _open_batch(self) -> None:
        BatchWindow(self)

    def _open_html(self) -> None:
        if self._html_path and Path(self._html_path).exists():
            webbrowser.open(f"file:///{Path(self._html_path).resolve()}")

    def _open_csv(self) -> None:
        if self._csv_path and Path(self._csv_path).exists():
            os.startfile(str(Path(self._csv_path).resolve()))

    def _open_history(self) -> None:
        HistoryWindow(self)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
