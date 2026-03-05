"""
Geradores de relatório: console (rich), HTML (jinja2) e CSV.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict

from .rules import Severity


# ─────────────────────────────────────────────────────────────────────────────
#  Console  (rich)
# ─────────────────────────────────────────────────────────────────────────────


def print_console_report(result: Dict) -> None:
    """Imprime o resultado no terminal usando rich."""
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()

    color = "green" if result["passed"] else "red"
    status = "✅  APROVADO" if result["passed"] else "❌  REPROVADO"

    console.print()
    console.print(
        Panel(
            f"[bold {color}]{status}[/bold {color}]\n\n"
            f"Arquivo : [cyan]{result['file']}[/cyan]\n"
            f"[red]Erros   : {result['errors']}[/red]   "
            f"[yellow]Avisos : {result['warnings']}[/yellow]   "
            f"[blue]Infos  : {result['infos']}[/blue]",
            title="[bold white]DWG Quality Checker[/bold white]",
            border_style=color,
            padding=(1, 2),
        )
    )

    if not result["issues"]:
        console.print("[bold green]\n  Nenhum problema encontrado! 🎉[/bold green]\n")
        return

    table = Table(
        title="Problemas Encontrados",
        box=box.ROUNDED,
        show_lines=True,
        expand=True,
    )
    table.add_column("Severidade", style="bold", width=12, justify="center")
    table.add_column("Regra", style="cyan", width=34)
    table.add_column("Mensagem")
    table.add_column("Layer", style="dim", width=18)
    table.add_column("Localização", style="dim", width=22)
    table.add_column("Detalhes", style="dim", width=30)

    _colors = {
        Severity.ERROR: "red",
        Severity.WARNING: "yellow",
        Severity.INFO: "blue",
    }

    for issue in result["issues"]:
        c = _colors.get(issue.severity, "white")
        table.add_row(
            f"[{c}]{issue.severity.value}[/{c}]",
            issue.rule,
            issue.message,
            issue.layer or "—",
            getattr(issue, "location", "") or "—",
            issue.details or "—",
        )

    console.print()
    console.print(table)
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
#  HTML  (jinja2)
# ─────────────────────────────────────────────────────────────────────────────


def generate_html_report(result: Dict, output_path: str | None = None) -> str:
    """Gera relatório em HTML usando o template Jinja2."""
    import json
    import sys
    from jinja2 import Environment, FileSystemLoader

    if getattr(sys, 'frozen', False):
        template_dir = Path(sys._MEIPASS) / "templates"
    else:
        template_dir = Path(__file__).parent.parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    template = env.get_template("report.html")

    html = template.render(
        result=result,
        Severity=Severity,
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    )

    if output_path is None:
        output_path = Path(result["file_path"]).stem + "_report.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return str(output_path)


# ─────────────────────────────────────────────────────────────────────────────
#  CSV
# ─────────────────────────────────────────────────────────────────────────────


def generate_csv_report(result: Dict, output_path: str | None = None) -> str:
    """Gera relatório em CSV (separado por ponto-e-vírgula, UTF-8 BOM)."""
    if output_path is None:
        output_path = Path(result["file_path"]).stem + "_report.csv"

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            ["Arquivo", "Severidade", "Regra", "Mensagem",
             "Tipo Entidade", "Layer", "Localização", "Handle", "Detalhes"]
        )
        for issue in result["issues"]:
            writer.writerow(
                [
                    result["file"],
                    issue.severity.value,
                    issue.rule,
                    issue.message,
                    issue.entity_type,
                    issue.layer,
                    getattr(issue, "location", ""),
                    issue.handle,
                    issue.details,
                ]
            )

    return str(output_path)
