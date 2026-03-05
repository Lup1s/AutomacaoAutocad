"""
checker/i18n.py — Internacionalização do DWG Quality Checker.

O idioma é definido pelo instalador (Inno Setup) que grava {app}\\lang.cfg:
    [app]
    language = pt-BR   (ou en)

Em runtime, chamar set_lang(get_lang()) antes de construir qualquer widget.
Usar _("chave") em todo string visível ao usuário.
"""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

# ── Localiza a pasta raiz do app (funciona frozen e dev) ─────────────────────
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).parent.parent

_LANG: str = "pt-BR"  # padrão; sobrescrito por set_lang()

# ─────────────────────────────────────────────────────────────────────────────
#  Dicionários de tradução
# ─────────────────────────────────────────────────────────────────────────────

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Português (Brasil) ───────────────────────────────────────────────────
    "pt-BR": {
        # Header
        "btn_history":       "📜  Histórico",
        "btn_watch":         "👁  Watch",
        "btn_compare":       "🔄  Comparar",
        "btn_config":        "⚙️  Config",
        "btn_about":         "ℹ️  Sobre",
        # Controles
        "label_file":        "Arquivo:",
        "btn_open":          "📂  Abrir",
        "btn_folder":        "📁 Pasta",
        "btn_verify":        "🔍  Verificar",
        "btn_html":          "📄 HTML",
        "btn_csv":           "📊 CSV",
        "btn_pdf":           "📑 PDF",
        "chk_auto_html":     "Auto HTML",
        "file_placeholder":  "Selecione ou arraste um arquivo .DXF ou .DWG aqui...",
        # Seleção de arquivo
        "file_select_title": "Selecionar arquivo CAD",
        "file_type_cad":     "Arquivos CAD",
        "file_type_dxf":     "DXF — Drawing Exchange Format",
        "file_type_dwg":     "DWG — AutoCAD Drawing",
        "file_type_all":     "Todos os arquivos",
        # Status / footer
        "status_ready":         "Pronto para verificar.",
        "status_verifying":     "Verificando...",
        "footer_ready":         "Pronto.",
        "footer_oda_convert":   "ODA: convertendo {file}...",
        "footer_sha":           "SHA-256: {sha}…",
        # Resultados
        "result_passed":    "✅  APROVADO",
        "result_failed":    "❌  REPROVADO",
        "col_datetime":     "Data/Hora",
        "col_file":         "Arquivo",
        "col_status":       "Status",
        "col_errors":       "Erros",
        "col_warnings":     "Avisos",
        "col_infos":        "Infos",
        "col_path":         "Caminho",
        "col_size":         "Tamanho",
        "col_dxf_ver":      "Versão DXF",
        "col_entities":     "Entidades",
        "col_duration":     "Duração",
        # Diálogos
        "dlg_no_file_title":       "Arquivo não selecionado",
        "dlg_no_file_msg":         "Selecione um arquivo .DXF ou .DWG válido.",
        "dlg_invalid_fmt_title":   "Formato inválido",
        "dlg_invalid_fmt_msg":     "Apenas arquivos .DXF e .DWG são suportados nesta versão.",
        "dlg_large_file_title":    "Arquivo grande",
        "dlg_large_file_msg":      "O arquivo tem {size:.0f} MB.\nA verificação pode levar vários minutos.\n\nContinuar?",
        "dlg_oda_title":           "Suporte a .DWG — ODA não encontrado",
        "dlg_oda_msg": (
            "Para verificar arquivos .DWG, instale o ODA File Converter (gratuito):\n\n"
            "  🔗 https://www.opendesign.com/guestfiles/oda_file_converter\n\n"
            "Após instalar, o software detectará automaticamente e converterá o\n"
            ".DWG para .DXF antes da verificação.\n\n"
            "─── Alternativa manual ───\n"
            "Converta no AutoCAD: Arquivo → Salvar Como → AutoCAD DXF (*.dxf)"
        ),
        # ODA
        "oda_converting":  "Convertendo {file} → DXF (ODA)...",
        # Histórico
        "history_title":   "Histórico de Verificações",
        "history_dblclick":"Duplo clique para abrir o relatório HTML",
        "history_no_html": "Relatório HTML não encontrado.",
        # Lote
        "batch_title":          "Verificação em Lote",
        "batch_select_folder":  "Selecionar pasta com arquivos DXF",
        "batch_placeholder":    "Selecione uma pasta com arquivos DXF...",
        "batch_btn_folder":     "📂 Pasta",
        "batch_btn_start":      "▶ Iniciar Lote",
        "batch_filter_label":   "Filtro:",
        "batch_filter_ph":      "Filtrar por nome...",
        "batch_found":          "{n} arquivo(s) DXF encontrado(s) — clique em Iniciar Lote",
        "batch_processing":     "Processando {cur}/{total}: {file}",
        "batch_done":           "Lote concluído: {ok} aprovados, {fail} reprovados.",
        "batch_dblclick":       "Duplo clique para abrir relatório HTML",
        # Watch
        "watch_title":          "👁️  Watch Folder",
        "watch_placeholder":    "Selecione uma pasta para monitorar...",
        "watch_btn_folder":     "📂 Pasta",
        "watch_btn_start":      "▶ Iniciar monitoramento",
        "watch_btn_stop":       "⏹ Parar monitoramento",
        "watch_interval_lbl":   "Intervalo (s):",
        "watch_status_stopped": "⏸  Monitoramento parado.",
        "watch_status_running": "▶  Monitorando — verificando a cada {interval}s",
        "watch_status_check":   "🔍  Verificando: {file}...",
        "watch_status_last":    "▶  Monitorando — último: {file}",
        "watch_col_time":       "Hora",
        "watch_col_file":       "Arquivo",
        "watch_col_status":     "Status",
        "watch_col_errors":     "Erros",
        "watch_col_warnings":   "Avisos",
        "watch_dblclick":       "Duplo clique para abrir o relatório HTML",
        "watch_invalid_folder": "Pasta inválida",
        "watch_invalid_msg":    "Selecione uma pasta válida.",
        "watch_passed":         "✅ OK",
        "watch_failed":         "❌ FALHOU",
        "watch_error_row":      "⚠️ ERRO",
        # Comparar
        "compare_title":        "🔄  Comparar Revisões",
        "compare_file_a":       "📄 Revisão anterior (A):",
        "compare_file_b":       "📄 Revisão nova (B):",
        "compare_btn":          "🔄  Comparar",
        "compare_btn_loading":  "⏳  Comparando...",
        "compare_select_msg":   "Selecione dois arquivos DXF para comparar.",
        "compare_loading_msg":  "Carregando arquivos...",
        "compare_result_msg":   "{name_a}  →  {name_b}  |  {total} diferença(s)",
        "compare_no_diff":      "{name_a}  →  {name_b}  |  Sem diferenças",
        "compare_no_files":     "Arquivos não selecionados",
        "compare_no_files_msg": "Selecione os dois arquivos DXF.",
        "compare_not_found":    "Arquivo não encontrado",
        "compare_filter_all":   "Todos",
        "compare_filter_add":   "Adicionado",
        "compare_filter_rem":   "Removido",
        "compare_filter_mod":   "Modificado",
        "compare_col_type":     "Tipo",
        "compare_col_layer":    "Layer",
        "compare_col_handle":   "Handle",
        "compare_col_detail":   "Detalhe",
        "compare_added_detail": "{type} adicionado na revisão B",
        "compare_removed_detail":"{type} removido da revisão B",
        "compare_error_title":  "Erro na comparação",
        "compare_diff_label":   "Diferenças",
        # Config
        "config_title":         "Configurações",
        "config_tab_general":   "⚙️ Geral",
        "config_tab_layers":    "🗂 Layers",
        "config_tab_drawing":   "📐 Desenho",
        "config_btn_save":      "💾 Salvar",
        "config_btn_close":     "✖ Fechar",
        "config_saved":         "Configurações salvas com sucesso.",
        "config_save_error":    "Erro ao salvar configurações:\n{error}",
        "config_profile_save":  "Salvar Perfil",
        "config_profile_load":  "Carregar",
        "config_profile_delete":"Excluir",
        "config_profile_ph":    "Nome do perfil...",
        "config_profile_empty": "Informe um nome para o perfil.",
        "config_profile_saved": "Perfil '{name}' salvo.",
        "config_profile_loaded":"Perfil '{name}' carregado.",
        "config_profile_deleted":"Perfil '{name}' excluído.",
        "config_profile_notfound":"Perfil não encontrado.",
        "config_profile_confirm":"Excluir o perfil '{name}'?",
        # Sobre
        "about_title":   "Sobre",
        "about_version": "Versão {version}",
        "about_desc":    "Verificador automático de qualidade para arquivos DXF/DWG.",
        "about_dev":     "Desenvolvido por",
        "about_close":   "Fechar",
        # Update
        "update_banner": "✨  Nova versão disponível: v{latest}  —  Clique para baixar",
        # ── HTML template ────────────────────────────────────────────────────
        "rpt_subtitle":       "Relatório de Verificação de Qualidade CAD",
        "rpt_status_pass":    "✅ Desenho aprovado — nenhum ERRO encontrado",
        "rpt_status_fail":    "❌ Desenho reprovado — {errors} erro(s) encontrado(s)",
        "rpt_generated":      "Gerado em",
        "rpt_entities":       "entidades",
        "rpt_errors_badge":   "Erro(s)",
        "rpt_warnings_badge": "Aviso(s)",
        "rpt_infos_badge":    "Info(s)",
        "rpt_viewer_title":   "🖥️ Mini AutoCAD",
        "rpt_fit":            "⊙ Encaixar",
        "rpt_grid":           "▦ Grid",
        "rpt_labels":         "🏷 Labels",
        "rpt_base":           "👁 Base",
        "rpt_errors_only":    "⚠ Só erros",
        "rpt_layers_btn":     "📋 Layers",
        "rpt_entities_leg":   "Entidades",
        "rpt_error_leg":      "Erro",
        "rpt_warning_leg":    "Aviso",
        "rpt_info_leg":       "Info",
        "rpt_scroll_hint":    "Scroll = zoom · Arrastar = mover · Clique na lista = destacar",
        "rpt_issues_panel":   "{total} ocorrência(s) — clique para destacar no visualizador",
        "rpt_no_issues":      "🎉 Nenhum problema encontrado!",
        "rpt_table_title":    "📊 Tabela Completa de Ocorrências",
        "rpt_filter_ph":      "🔎 Filtrar...",
        "rpt_filter_all":     "Todos",
        "rpt_col_severity":   "Severidade",
        "rpt_col_rule":       "Regra",
        "rpt_col_message":    "Mensagem",
        "rpt_col_layer":      "Layer",
        "rpt_col_location":   "Localização",
        "rpt_col_details":    "Detalhes",
        "rpt_all_layers":     "Todos",
        "rpt_no_layers":      "Nenhum",
        "rpt_no_entities":    "Sem entidades",
        "rpt_footer_dev":     "Desenvolvido por",
        "rpt_js_with_error":  "com erro",
        "rpt_js_normal":      "normais",
        "rpt_js_total":       "total",
        "rpt_js_zoom":        "Zoom",
        # ── PDF ──────────────────────────────────────────────────────────────
        "pdf_subject":      "Relatório de Qualidade CAD",
        "pdf_passed":       "APROVADO",
        "pdf_failed":       "REPROVADO",
        "pdf_file":         "Arquivo:",
        "pdf_path":         "Caminho:",
        "pdf_size":         "Tamanho:",
        "pdf_dxf_version":  "Versão DXF:",
        "pdf_entities":     "Entidades:",
        "pdf_duration":     "Duração:",
        "pdf_checked_at":   "Verificado:",
        "pdf_sha256":       "SHA-256:",
        "pdf_errors":       "Erros",
        "pdf_warnings":     "Avisos",
        "pdf_infos":        "Infos",
        "pdf_total":        "Total",
        "pdf_issues_title": "Problemas Encontrados",
        "pdf_no_issues":    "🎉  Nenhum problema encontrado!",
        "pdf_col_severity": "Severidade",
        "pdf_col_rule":     "Regra",
        "pdf_col_message":  "Mensagem",
        "pdf_col_layer":    "Layer",
        "pdf_col_handle":   "Handle",
        # ── CSV ──────────────────────────────────────────────────────────────
        "csv_file":         "Arquivo",
        "csv_severity":     "Severidade",
        "csv_rule":         "Regra",
        "csv_message":      "Mensagem",
        "csv_entity_type":  "Tipo Entidade",
        "csv_layer":        "Layer",
        "csv_location":     "Localização",
        "csv_handle":       "Handle",
        "csv_details":      "Detalhes",
        # Notificações desktop (Watch Folder)
        "notify_pass":      "✅ Aprovado — nenhum erro encontrado",
        "notify_fail":      "❌ Reprovado — {n} erro(s) encontrado(s)",
        # Gráfico de tendência (Histórico)
        "chart_title":      "📈 Tendência de Qualidade",
        "chart_no_data":    "Sem dados suficientes (mínimo 2 verificações)",
        "chart_errors":     "Erros",
        # Perfis de disciplina
        "profile_arch":     "Arquitetura (NBR 6492)",
        "profile_topo":     "Topografia",
        "profile_struct":   "Estrutural",
        "profile_mep":      "Instalações (MEP)",
        # Excel
        "excel_sheet_summary": "Resumo",
        "excel_sheet_issues":  "Ocorrências",
        "excel_sheet_bylayer": "Por Layer",
        # Anotação DXF
        "btn_annotate":         "🏷 Anotar DXF",
        "annotate_done":        "DXF anotado salvo em:\n{path}",
        "annotate_error":       "Erro ao anotar DXF:\n{err}",
        "annotate_no_result":   "Verifique um arquivo antes de anotar.",
        # Dashboard de lote
        "btn_dashboard":        "📊 Dashboard",
        # Aba de novas regras
        "tab_extra_rules":      "⚡  Novas Regras",
        "extra_rules_header":   "Novas regras v2.5 — ative/desative e ajuste a severidade",
        "sev_inherit":          "Herdado",
        # Comparação visual
        "compare_canvas_legend": "🟢 Adicionado   🔴 Removido   🟡 Modificado   ⬛ Igual",
    },

    # ── English ──────────────────────────────────────────────────────────────
    "en": {
        # Header
        "btn_history":       "📜  History",
        "btn_watch":         "👁  Watch",
        "btn_compare":       "🔄  Compare",
        "btn_config":        "⚙️  Config",
        "btn_about":         "ℹ️  About",
        # Controls
        "label_file":        "File:",
        "btn_open":          "📂  Open",
        "btn_folder":        "📁 Folder",
        "btn_verify":        "🔍  Verify",
        "btn_html":          "📄 HTML",
        "btn_csv":           "📊 CSV",
        "btn_pdf":           "📑 PDF",
        "btn_xlsx":          "📈 XLSX",
        "chk_auto_html":     "Auto HTML",
        "file_placeholder":  "Select or drag a .DXF or .DWG file here...",
        # File selection
        "file_select_title": "Select CAD file",
        "file_type_cad":     "CAD Files",
        "file_type_dxf":     "DXF — Drawing Exchange Format",
        "file_type_dwg":     "DWG — AutoCAD Drawing",
        "file_type_all":     "All files",
        # Status / footer
        "status_ready":         "Ready to verify.",
        "status_verifying":     "Verifying...",
        "footer_ready":         "Ready.",
        "footer_oda_convert":   "ODA: converting {file}...",
        "footer_sha":           "SHA-256: {sha}…",
        # Results
        "result_passed":    "✅  PASSED",
        "result_failed":    "❌  FAILED",
        "col_datetime":     "Date/Time",
        "col_file":         "File",
        "col_status":       "Status",
        "col_errors":       "Errors",
        "col_warnings":     "Warnings",
        "col_infos":        "Infos",
        "col_path":         "Path",
        "col_size":         "Size",
        "col_dxf_ver":      "DXF Version",
        "col_entities":     "Entities",
        "col_duration":     "Duration",
        # Dialogs
        "dlg_no_file_title":       "No file selected",
        "dlg_no_file_msg":         "Please select a valid .DXF or .DWG file.",
        "dlg_invalid_fmt_title":   "Invalid format",
        "dlg_invalid_fmt_msg":     "Only .DXF and .DWG files are supported in this version.",
        "dlg_large_file_title":    "Large file",
        "dlg_large_file_msg":      "The file is {size:.0f} MB.\nVerification may take several minutes.\n\nContinue?",
        "dlg_oda_title":           ".DWG Support — ODA not found",
        "dlg_oda_msg": (
            "To verify .DWG files, install ODA File Converter (free):\n\n"
            "  🔗 https://www.opendesign.com/guestfiles/oda_file_converter\n\n"
            "After installing, the software will automatically detect and convert\n"
            ".DWG to .DXF before verification.\n\n"
            "─── Manual alternative ───\n"
            "Convert in AutoCAD: File → Save As → AutoCAD DXF (*.dxf)"
        ),
        # ODA
        "oda_converting":  "Converting {file} → DXF (ODA)...",
        # History
        "history_title":   "Verification History",
        "history_dblclick":"Double-click to open the HTML report",
        "history_no_html": "HTML report not found.",
        # Batch
        "batch_title":          "Batch Verification",
        "batch_select_folder":  "Select folder with DXF files",
        "batch_placeholder":    "Select a folder with DXF files...",
        "batch_btn_folder":     "📂 Folder",
        "batch_btn_start":      "▶ Start Batch",
        "batch_filter_label":   "Filter:",
        "batch_filter_ph":      "Filter by name...",
        "batch_found":          "{n} DXF file(s) found — click Start Batch",
        "batch_processing":     "Processing {cur}/{total}: {file}",
        "batch_done":           "Batch done: {ok} passed, {fail} failed.",
        "batch_dblclick":       "Double-click to open HTML report",
        # Watch
        "watch_title":          "👁️  Watch Folder",
        "watch_placeholder":    "Select a folder to monitor...",
        "watch_btn_folder":     "📂 Folder",
        "watch_btn_start":      "▶ Start monitoring",
        "watch_btn_stop":       "⏹ Stop monitoring",
        "watch_interval_lbl":   "Interval (s):",
        "watch_status_stopped": "⏸  Monitoring stopped.",
        "watch_status_running": "▶  Monitoring — checking every {interval}s",
        "watch_status_check":   "🔍  Checking: {file}...",
        "watch_status_last":    "▶  Monitoring — last: {file}",
        "watch_col_time":       "Time",
        "watch_col_file":       "File",
        "watch_col_status":     "Status",
        "watch_col_errors":     "Errors",
        "watch_col_warnings":   "Warnings",
        "watch_dblclick":       "Double-click to open the HTML report",
        "watch_invalid_folder": "Invalid folder",
        "watch_invalid_msg":    "Please select a valid folder.",
        "watch_passed":         "✅ OK",
        "watch_failed":         "❌ FAILED",
        "watch_error_row":      "⚠️ ERROR",
        # Compare
        "compare_title":        "🔄  Compare Revisions",
        "compare_file_a":       "📄 Previous revision (A):",
        "compare_file_b":       "📄 New revision (B):",
        "compare_btn":          "🔄  Compare",
        "compare_btn_loading":  "⏳  Comparing...",
        "compare_select_msg":   "Select two DXF files to compare.",
        "compare_loading_msg":  "Loading files...",
        "compare_result_msg":   "{name_a}  →  {name_b}  |  {total} difference(s)",
        "compare_no_diff":      "{name_a}  →  {name_b}  |  No differences",
        "compare_no_files":     "Files not selected",
        "compare_no_files_msg": "Please select both DXF files.",
        "compare_not_found":    "File not found",
        "compare_filter_all":   "All",
        "compare_filter_add":   "Added",
        "compare_filter_rem":   "Removed",
        "compare_filter_mod":   "Modified",
        "compare_col_type":     "Type",
        "compare_col_layer":    "Layer",
        "compare_col_handle":   "Handle",
        "compare_col_detail":   "Detail",
        "compare_added_detail": "{type} added in revision B",
        "compare_removed_detail":"{type} removed from revision B",
        "compare_error_title":  "Comparison error",
        "compare_diff_label":   "Differences",
        # Config
        "config_title":         "Settings",
        "config_tab_general":   "⚙️ General",
        "config_tab_layers":    "🗂 Layers",
        "config_tab_drawing":   "📐 Drawing",
        "config_btn_save":      "💾 Save",
        "config_btn_close":     "✖ Close",
        "config_saved":         "Settings saved successfully.",
        "config_save_error":    "Error saving settings:\n{error}",
        "config_profile_save":  "Save Profile",
        "config_profile_load":  "Load",
        "config_profile_delete":"Delete",
        "config_profile_ph":    "Profile name...",
        "config_profile_empty": "Please enter a profile name.",
        "config_profile_saved": "Profile '{name}' saved.",
        "config_profile_loaded":"Profile '{name}' loaded.",
        "config_profile_deleted":"Profile '{name}' deleted.",
        "config_profile_notfound":"Profile not found.",
        "config_profile_confirm":"Delete profile '{name}'?",
        # About
        "about_title":   "About",
        "about_version": "Version {version}",
        "about_desc":    "Automated quality checker for DXF/DWG CAD files.",
        "about_dev":     "Developed by",
        "about_close":   "Close",
        # Update
        "update_banner": "✨  New version available: v{latest}  —  Click to download",
        # ── HTML template ────────────────────────────────────────────────────
        "rpt_subtitle":       "CAD Quality Verification Report",
        "rpt_status_pass":    "✅ Drawing passed — no ERRORs found",
        "rpt_status_fail":    "❌ Drawing failed — {errors} error(s) found",
        "rpt_generated":      "Generated at",
        "rpt_entities":       "entities",
        "rpt_errors_badge":   "Error(s)",
        "rpt_warnings_badge": "Warning(s)",
        "rpt_infos_badge":    "Info(s)",
        "rpt_viewer_title":   "🖥️ Mini AutoCAD",
        "rpt_fit":            "⊙ Fit",
        "rpt_grid":           "▦ Grid",
        "rpt_labels":         "🏷 Labels",
        "rpt_base":           "👁 Base",
        "rpt_errors_only":    "⚠ Issues only",
        "rpt_layers_btn":     "📋 Layers",
        "rpt_entities_leg":   "Entities",
        "rpt_error_leg":      "Error",
        "rpt_warning_leg":    "Warning",
        "rpt_info_leg":       "Info",
        "rpt_scroll_hint":    "Scroll = zoom · Drag = pan · Click list = highlight",
        "rpt_issues_panel":   "{total} issue(s) — click to highlight in viewer",
        "rpt_no_issues":      "🎉 No issues found!",
        "rpt_table_title":    "📊 Full Issues Table",
        "rpt_filter_ph":      "🔎 Filter...",
        "rpt_filter_all":     "All",
        "rpt_col_severity":   "Severity",
        "rpt_col_rule":       "Rule",
        "rpt_col_message":    "Message",
        "rpt_col_layer":      "Layer",
        "rpt_col_location":   "Location",
        "rpt_col_details":    "Details",
        "rpt_all_layers":     "All",
        "rpt_no_layers":      "None",
        "rpt_no_entities":    "No entities",
        "rpt_footer_dev":     "Developed by",
        "rpt_js_with_error":  "with error",
        "rpt_js_normal":      "normal",
        "rpt_js_total":       "total",
        "rpt_js_zoom":        "Zoom",
        # ── PDF ──────────────────────────────────────────────────────────────
        "pdf_subject":      "CAD Quality Report",
        "pdf_passed":       "PASSED",
        "pdf_failed":       "FAILED",
        "pdf_file":         "File:",
        "pdf_path":         "Path:",
        "pdf_size":         "Size:",
        "pdf_dxf_version":  "DXF Version:",
        "pdf_entities":     "Entities:",
        "pdf_duration":     "Duration:",
        "pdf_checked_at":   "Checked at:",
        "pdf_sha256":       "SHA-256:",
        "pdf_errors":       "Errors",
        "pdf_warnings":     "Warnings",
        "pdf_infos":        "Infos",
        "pdf_total":        "Total",
        "pdf_issues_title": "Issues Found",
        "pdf_no_issues":    "🎉  No issues found!",
        "pdf_col_severity": "Severity",
        "pdf_col_rule":     "Rule",
        "pdf_col_message":  "Message",
        "pdf_col_layer":    "Layer",
        "pdf_col_handle":   "Handle",
        # ── CSV ──────────────────────────────────────────────────────────────
        "csv_file":         "File",
        "csv_severity":     "Severity",
        "csv_rule":         "Rule",
        "csv_message":      "Message",
        "csv_entity_type":  "Entity Type",
        "csv_layer":        "Layer",
        "csv_location":     "Location",
        "csv_handle":       "Handle",
        "csv_details":      "Details",
        # Desktop notifications (Watch Folder)
        "notify_pass":      "✅ Passed — no errors found",
        "notify_fail":      "❌ Failed — {n} error(s) found",
        # Trend chart (History)
        "chart_title":      "📈 Quality Trend",
        "chart_no_data":    "Not enough data (minimum 2 verifications)",
        "chart_errors":     "Errors",
        # Discipline profiles
        "profile_arch":     "Architecture (NBR 6492)",
        "profile_topo":     "Topography",
        "profile_struct":   "Structural",
        "profile_mep":      "MEP Installations",
        # Excel
        "excel_sheet_summary": "Summary",
        "excel_sheet_issues":  "Issues",
        "excel_sheet_bylayer": "By Layer",
        # DXF Annotation
        "btn_annotate":         "🏷 Annotate DXF",
        "annotate_done":        "Annotated DXF saved at:\n{path}",
        "annotate_error":       "Error annotating DXF:\n{err}",
        "annotate_no_result":   "Verify a file before annotating.",
        # Batch dashboard
        "btn_dashboard":        "📊 Dashboard",
        # Extra rules tab
        "tab_extra_rules":      "⚡  New Rules",
        "extra_rules_header":   "New rules v2.5 — enable/disable and adjust severity",
        "sev_inherit":          "Inherited",
        # Visual compare
        "compare_canvas_legend": "🟢 Added   🔴 Removed   🟡 Modified   ⬛ Unchanged",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  API pública
# ─────────────────────────────────────────────────────────────────────────────

def get_lang() -> str:
    """Lê o idioma do lang.cfg gravado pelo instalador."""
    cfg_file = _BASE_DIR / "lang.cfg"
    if cfg_file.exists():
        try:
            cp = configparser.ConfigParser()
            cp.read(str(cfg_file), encoding="utf-8")
            return cp.get("app", "language", fallback="pt-BR")
        except Exception:
            pass
    return "pt-BR"


def set_lang(lang: str) -> None:
    """Define o idioma ativo para toda a sessão."""
    global _LANG
    _LANG = lang if lang in TRANSLATIONS else "pt-BR"


def _(key: str, **kwargs) -> str:
    """Retorna o string traduzido para o idioma atual. Suporta .format(**kwargs)."""
    table = TRANSLATIONS.get(_LANG, TRANSLATIONS["pt-BR"])
    text = table.get(key, TRANSLATIONS["pt-BR"].get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def get_tr_dict() -> dict[str, str]:
    """Retorna o dicionário completo para injetar em templates Jinja2."""
    return TRANSLATIONS.get(_LANG, TRANSLATIONS["pt-BR"])
