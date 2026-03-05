"""
DWG Quality Checker — CLI entry point

Exemplos de uso:
  python main.py planta.dxf
  python main.py planta.dxf --output html
  python main.py planta.dxf --output all --output-file relatorio
  python main.py planta.dxf --config padrao_empresa.yaml --strict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from checker.core import DXFChecker
from checker.report import generate_csv_report, generate_html_report, print_console_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dwg-checker",
        description="🏗️  DWG/DXF Quality Checker — Verificação automatizada de qualidade CAD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
exemplos:
  python main.py planta.dxf
  python main.py planta.dxf --output html
  python main.py planta.dxf --output all --output-file relatorio
  python main.py planta.dxf --config meu_padrao.yaml --strict
        """,
    )
    parser.add_argument("file", help="Caminho para o arquivo DXF/DWG")
    parser.add_argument(
        "--output", "-o",
        choices=["console", "html", "csv", "all"],
        default="console",
        help="Formato de saída (padrão: console)",
    )
    parser.add_argument(
        "--output-file", "-f",
        metavar="NOME",
        help="Nome base para o arquivo de saída (sem extensão)",
    )
    parser.add_argument(
        "--config", "-c",
        metavar="ARQUIVO",
        help="Caminho para um arquivo de configuração YAML customizado",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Retorna exit code 1 se houver qualquer ERRO (útil em CI/CD)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # ── Carrega o checker ────────────────────────────────────────────────────
    try:
        checker = DXFChecker(config_path=args.config)
    except FileNotFoundError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 2

    # ── Executa a verificação ────────────────────────────────────────────────
    try:
        result = checker.check(args.file)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 2

    # ── Gera as saídas ───────────────────────────────────────────────────────
    if args.output in ("console", "all"):
        print_console_report(result)

    if args.output in ("html", "all"):
        out = (args.output_file + ".html") if args.output_file else None
        path = generate_html_report(result, out)
        print(f"📄 Relatório HTML gerado: {path}")

    if args.output in ("csv", "all"):
        out = (args.output_file + ".csv") if args.output_file else None
        path = generate_csv_report(result, out)
        print(f"📊 Relatório CSV  gerado: {path}")

    # ── Exit code ─────────────────────────────────────────────────────────────
    if args.strict and result["errors"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
