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

import json
import sys
import time
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from checker.version import APP_VERSION


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="dwg-checker",
        description=f"DWG Quality Checker v{APP_VERSION} — modo CLI",
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
    parser.add_argument("--profile", metavar="NAME", default=None, action="append",
                        help="Perfil de norma/disciplina para esta execução (repita a opção ou use vírgulas)")
    parser.add_argument("--profiles-file", metavar="FILE", default=None,
                        help="Arquivo JSON de perfis (padrão: config_profiles.json ao lado do config)")
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
    parser.add_argument("--timeout-seconds", type=float, default=0.0,
                        help="Timeout por arquivo em segundos (0 = sem timeout)")
    parser.add_argument("--json-log", metavar="FILE", default=None,
                        help="Arquivo JSONL para log estruturado por arquivo processado")
    parser.add_argument("--summary-json", metavar="FILE", default=None,
                        help="Arquivo JSON com resumo agregado da execução")
    parser.add_argument("--no-cache", action="store_true",
                        help="Desativa cache por SHA-256 para arquivos duplicados no mesmo lote")
    args = parser.parse_args()

    # ── Importações pesadas só aqui ───────────────────────────────────────────
    from checker.core import DXFChecker, merge_profiles_into_config
    from checker.report import (
        generate_csv_report,
        generate_excel_report,
        generate_html_report,
        generate_pdf_report,
    )

    def _resolve_profiles_file(config_path: str | None, profiles_file: str | None) -> Path:
        if profiles_file:
            return Path(profiles_file)
        if config_path:
            return Path(config_path).parent / "config_profiles.json"
        return Path(__file__).resolve().parents[1] / "config_profiles.json"

    def _load_profiles(path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}

    def _normalize_profile_names(raw_profiles: list[str] | None) -> list[str]:
        if not raw_profiles:
            return []
        names: list[str] = []
        for raw in raw_profiles:
            if not isinstance(raw, str):
                continue
            for part in raw.split(","):
                name = part.strip()
                if name and name not in names:
                    names.append(name)
        return names

    try:
        checker_config_data = None
        selected_profiles = _normalize_profile_names(args.profile)
        if selected_profiles:
            checker_base = DXFChecker(args.config)
            profiles_path = _resolve_profiles_file(args.config, args.profiles_file)
            profiles = _load_profiles(profiles_path)
            missing = [name for name in selected_profiles if not isinstance(profiles.get(name), dict)]
            if missing:
                available = ", ".join(sorted(profiles.keys())) if profiles else "(nenhum perfil)"
                raise ValueError(
                    f"Perfil(is) não encontrado(s) em '{profiles_path}': {', '.join(missing)}. "
                    f"Disponíveis: {available}"
                )
            profile_cfg_list = [profiles[name] for name in selected_profiles]
            checker_config_data = merge_profiles_into_config(checker_base.config, profile_cfg_list)

        checker = DXFChecker(args.config, config_data=checker_config_data)
    except Exception as exc:
        if args.json:
            import json as _json
            print(_json.dumps([{"file": "*", "error": f"Falha ao carregar configuração: {exc}"}], ensure_ascii=False, indent=2))
        else:
            print(f"[ERRO] Falha ao carregar configuração: {exc}", file=sys.stderr)
        sys.exit(1)

    results_json: list = []
    any_fail = False
    run_t0 = time.perf_counter()
    cache_by_hash: dict[str, dict] = {}
    stats = {
        "files_total": len(args.files),
        "processed": 0,
        "passed": 0,
        "failed": 0,
        "errored": 0,
        "cache_hits": 0,
        "reports_generated": 0,
    }

    def _sha256_of(path: Path) -> str:
        h = sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _write_summary_file(summary: dict) -> None:
        if not args.summary_json:
            return
        p = Path(args.summary_json)
        if p.parent and not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    def _append_json_log(event: dict) -> None:
        if not args.json_log:
            return
        try:
            log_path = Path(args.json_log)
            if log_path.parent and not log_path.parent.exists():
                log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as exc:
            if not args.quiet:
                print(f"  [AVISO] JSON log: {exc}", file=sys.stderr)

    def _run_check(path: Path):
        timeout = args.timeout_seconds or 0.0
        if timeout <= 0:
            return checker.check(str(path))

        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(checker.check, str(path))
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"Timeout de {timeout:.2f}s excedido para '{path.name}'") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    for fp in args.files:
        stats["processed"] += 1
        path = Path(fp)
        if not path.exists():
            if not args.quiet:
                print(f"[ERRO] Arquivo não encontrado: {fp}", file=sys.stderr)
            any_fail = True
            stats["errored"] += 1
            if args.json:
                results_json.append({"file": str(fp), "error": "Arquivo não encontrado"})
            _append_json_log({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "file": str(fp),
                "status": "error",
                "error": "Arquivo não encontrado",
            })
            continue

        if not args.quiet:
            print("─" * 60)
            print(f"  Verificando: {path.name}")

        hash_key = ""
        from_cache = False
        try:
            if not args.no_cache:
                hash_key = _sha256_of(path)
                if hash_key in cache_by_hash:
                    cached = cache_by_hash[hash_key]
                    result = {
                        **cached,
                        "file": path.name,
                        "file_path": str(path.resolve()),
                        "file_size_mb": round(path.stat().st_size / (1024 * 1024), 2),
                        "check_time": 0.0,
                        "sha256": hash_key,
                    }
                    from_cache = True
                    stats["cache_hits"] += 1
                else:
                    result = _run_check(path)
                    cache_by_hash[hash_key or result.get("sha256", "")] = dict(result)
            else:
                result = _run_check(path)
        except Exception as exc:
            if not args.quiet:
                print(f"  [ERRO] {exc}", file=sys.stderr)
            any_fail = True
            stats["errored"] += 1
            if args.json:
                results_json.append({"file": str(fp), "error": str(exc)})
            _append_json_log({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "file": str(fp),
                "status": "error",
                "error": str(exc),
            })
            continue

        # ── Relatórios ────────────────────────────────────────────────────────
        out_dir = Path(args.out_dir) if args.out_dir else path.parent
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            if not args.quiet:
                print(f"  [ERRO] Não foi possível criar pasta de saída '{out_dir}': {exc}", file=sys.stderr)
            any_fail = True
            stats["errored"] += 1
            if args.json:
                results_json.append({
                    "file": str(path),
                    "passed": False,
                    "errors": result.get("errors", 0),
                    "warnings": result.get("warnings", 0),
                    "infos": result.get("infos", 0),
                    "reports": [],
                    "sha256": result.get("sha256", ""),
                    "error": f"Falha ao criar pasta de saída: {exc}",
                })
            continue

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
                        stats["reports_generated"] += 1
                except Exception as e:
                    if not args.quiet:
                        print(f"  [AVISO] {fmt_key.upper()}: {e}")

        if args.annotate:
            try:
                from checker.annotate import annotate_dxf
                ann_path = str(out_dir / (path.stem + "_annotated.dxf"))
                annotate_dxf(result, ann_path)
                generated.append(Path(ann_path).name)
                stats["reports_generated"] += 1
            except Exception as e:
                if not args.quiet:
                    print(f"  [AVISO] Annotate: {e}")

        # ── Saída ─────────────────────────────────────────────────────────────
        passed = result["passed"]
        if not passed:
            any_fail = True
            stats["failed"] += 1
        else:
            stats["passed"] += 1

        _append_json_log({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "file": result["file"],
            "status": "passed" if passed else "failed",
            "errors": result["errors"],
            "warnings": result["warnings"],
            "infos": result["infos"],
            "reports": generated,
            "sha256": result.get("sha256", ""),
            "cached": from_cache,
        })

        if args.json:
            results_json.append({
                "file":     result["file"],
                "passed":   passed,
                "errors":   result["errors"],
                "warnings": result["warnings"],
                "infos":    result["infos"],
                "reports":  generated,
                "sha256":   result.get("sha256", ""),
                "cached":   from_cache,
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
            if from_cache:
                print("     Origem:   cache por conteúdo (SHA-256)")
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

    summary = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "duration_seconds": round(time.perf_counter() - run_t0, 3),
        "files_total": stats["files_total"],
        "processed": stats["processed"],
        "passed": stats["passed"],
        "failed": stats["failed"],
        "errored": stats["errored"],
        "cache_hits": stats["cache_hits"],
        "reports_generated": stats["reports_generated"],
        "cache_enabled": not args.no_cache,
        "exit_code": 1 if any_fail else 0,
    }
    try:
        _write_summary_file(summary)
    except Exception as exc:
        if not args.quiet:
            print(f"[AVISO] Falha ao gravar summary JSON: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(results_json, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print("─" * 60)
        print("Resumo:")
        print(f"  Processados: {summary['processed']}/{summary['files_total']}")
        print(f"  Aprovados:   {summary['passed']}")
        print(f"  Reprovados:  {summary['failed']}")
        print(f"  Com erro:    {summary['errored']}")
        print(f"  Cache hits:  {summary['cache_hits']}")
        print(f"  Relatórios:  {summary['reports_generated']}")
        print(f"  Duração:     {summary['duration_seconds']}s")

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
