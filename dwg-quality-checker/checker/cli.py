"""Modo CLI do DWG Quality Checker.

Uso:
  python launcher.py --cli arquivo.dxf [opções]
  python -m checker.cli arquivo.dxf [opções]

Exemplos:
  python launcher.py --cli planta.dxf
  python launcher.py --cli planta.dxf --output all --out-dir ./rel
  python launcher.py --cli *.dxf --quiet          # CI/CD: exit 0=OK 1=ERRO
  python launcher.py --cli planta.dxf --annotate  # gera DXF anotado
  python launcher.py --cli planta.dxf --json      # saída JSON para automação
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="dwg-checker",
        description="DWG Quality Checker v2.5.0 — modo CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemplos:
  python launcher.py --cli planta.dxf
  python launcher.py --cli planta.dxf --output all --out-dir ./rel
  python launcher.py --cli *.dxf --quiet     (CI/CD: exit 0=OK, 1=ERRO)
  python launcher.py --cli planta.dxf --annotate --json
        """,
    )
    parser.add_argument("files", nargs="+", metavar="FILE",
                        help="Arquivo(s) DXF a verificar")
    parser.add_argument("--config",   metavar="CFG",  default=None,
                        help="config.yaml personalizado")
    parser.add_argument("--output",   metavar="FMT",
                        choices=["html", "csv", "pdf", "xlsx", "all"],
                        default="html",
                        help="Formato de relatório (padrão: html)")
    parser.add_argument("--out-dir",  metavar="DIR",  default=None,
                        help="Pasta de saída para os relatórios")
    parser.add_argument("--annotate", action="store_true",
                        help="Gerar DXF anotado com layer _QC_ISSUES")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suprimir saída verbose")
    parser.add_argument("--json", action="store_true",
                        help="Saída em JSON (para integração/automação)")
    args = parser.parse_args()

    # ── Importações pesadas só aqui ───────────────────────────────────────────
    from checker.core import DXFChecker
    from checker.report import (
        generate_csv_report,
        generate_excel_report,
        generate_html_report,
        generate_pdf_report,
    )

    results_json: list = []
    any_fail = False

    for fp in args.files:
        path = Path(fp)
        if not path.exists():
            if not args.quiet:
                print(f"[ERRO] Arquivo não encontrado: {fp}", file=sys.stderr)
            any_fail = True
            continue

        if not args.quiet:
            print("─" * 60)
            print(f"  Verificando: {path.name}")

        try:
            checker = DXFChecker(args.config)
            result  = checker.check(str(path))
        except Exception as exc:
            if not args.quiet:
                print(f"  [ERRO] {exc}", file=sys.stderr)
            any_fail = True
            if args.json:
                results_json.append({"file": str(fp), "error": str(exc)})
            continue

        # ── Relatórios ────────────────────────────────────────────────────────
        out_dir = Path(args.out_dir) if args.out_dir else path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        base      = str(out_dir / (path.stem + "_report"))
        fmt       = args.output
        generated: list[str] = []

        for fmt_key, fn, ext in [
            ("html", generate_html_report,  ".html"),
            ("csv",  generate_csv_report,   ".csv"),
            ("pdf",  generate_pdf_report,   ".pdf"),
            ("xlsx", generate_excel_report, ".xlsx"),
        ]:
            if fmt in (fmt_key, "all"):
                try:
                    p = fn(result, base + ext)
                    if p:
                        generated.append(Path(p).name)
                except Exception as e:
                    if not args.quiet:
                        print(f"  [AVISO] {fmt_key.upper()}: {e}")

        if args.annotate:
            try:
                from checker.annotate import annotate_dxf
                ann_path = str(out_dir / (path.stem + "_annotated.dxf"))
                annotate_dxf(result, ann_path)
                generated.append(Path(ann_path).name)
            except Exception as e:
                if not args.quiet:
                    print(f"  [AVISO] Annotate: {e}")

        # ── Saída ─────────────────────────────────────────────────────────────
        passed = result["passed"]
        if not passed:
            any_fail = True

        if args.json:
            results_json.append({
                "file":     result["file"],
                "passed":   passed,
                "errors":   result["errors"],
                "warnings": result["warnings"],
                "infos":    result["infos"],
                "reports":  generated,
                "sha256":   result.get("sha256", ""),
                "issues": [
                    {
                        "rule":     i.rule,
                        "severity": i.severity.value,
                        "message":  i.message,
                        "layer":    i.layer,
                        "handle":   i.handle,
                        "location": i.location,
                    }
                    for i in result["issues"]
                    if i.severity.value == "ERROR"
                ],
            })
        elif not args.quiet:
            icon = "✅" if passed else "❌"
            print(f"  {icon} {'APROVADO' if passed else 'REPROVADO'}")
            print(f"     Erros:    {result['errors']}")
            print(f"     Avisos:   {result['warnings']}")
            print(f"     Infos:    {result['infos']}")
            if result["errors"] > 0:
                errs = [i for i in result["issues"] if i.severity.value == "ERROR"]
                print("     Top erros:")
                for i in errs[:5]:
                    loc = f"  @ {i.location}" if i.location else ""
                    print(f"       • [{i.rule}] {i.message[:65]}{loc}")
                if len(errs) > 5:
                    print(f"       … e mais {len(errs) - 5} erro(s)")
            if generated:
                print(f"     Relatórios: {', '.join(generated)}")

    if args.json:
        import json as _json
        print(_json.dumps(results_json, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print("─" * 60)

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
