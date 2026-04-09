"""
Ferramentas de recuperação para arquivos DXF com inconsistências.

Escopo atual:
- Recuperação de leitura com ``ezdxf.recover``;
- Auditoria e correções automáticas básicas;
- Limpeza opcional de RegApps e linetypes DGN;
- Diagnóstico de sintomas comuns (proxy, coordenadas gigantes, escala excessiva).
- Diagnóstico de referências externas (XREF), incluindo detecção de ciclo.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import shutil

import ezdxf
from ezdxf import recover


_DGN_KEYWORDS = ("DGN", "MS_", "MICROSTATION")
_REGAPP_KEEP = {"ACAD", "ACADANNOTATIVE"}
_XREF_FLAG_BITS = 4 | 8
_RECOVERY_MODES = {"safe", "balanced", "aggressive"}


@dataclass
class RecoveryIssue:
    category: str
    level: str
    message: str
    recommendation: str = ""


def _compute_health_score(stats: dict[str, Any]) -> int:
    """Calcula score de saúde (0–100), maior é melhor."""
    score = 100.0

    score -= min(35.0, float(stats.get("load_errors", 0)) * 6.0)
    score -= min(18.0, float(stats.get("proxy_entities", 0)) * 1.2)
    score -= min(20.0, float(stats.get("regapps_before", 0)) / 12.0)
    score -= min(8.0, float(stats.get("dgn_linetypes_before", 0)) * 1.0)
    score -= min(12.0, float(stats.get("annotative_scales", 0)) / 80.0)
    score -= min(14.0, float(stats.get("xref_cycles", 0)) * 7.0)
    score -= min(10.0, float(stats.get("xref_missing", 0)) * 2.5)

    max_abs = float(stats.get("max_abs_coord", 0.0) or 0.0)
    if max_abs > 1_000_000:
        score -= min(14.0, (max_abs - 1_000_000) / 250_000)

    return int(max(0, min(100, round(score))))


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _entity_points(entity) -> list[tuple[float, float]]:
    """Extrai pontos 2D representativos de algumas entidades comuns."""
    pts: list[tuple[float, float]] = []
    t = entity.dxftype()

    try:
        if t == "LINE":
            for p in (entity.dxf.start, entity.dxf.end):
                pts.append((float(p.x), float(p.y)))
        elif t in {"CIRCLE", "ARC", "ELLIPSE"}:
            c = entity.dxf.center
            pts.append((float(c.x), float(c.y)))
        elif t in {"POINT", "TEXT", "MTEXT", "INSERT"}:
            p = entity.dxf.insert if hasattr(entity.dxf, "insert") else None
            if p is not None:
                pts.append((float(p.x), float(p.y)))
        elif t == "LWPOLYLINE":
            for p in entity.get_points("xy"):
                pts.append((float(p[0]), float(p[1])))
        elif t == "POLYLINE":
            for v in entity.vertices:
                p = v.dxf.location
                pts.append((float(p.x), float(p.y)))
    except Exception:
        return []

    return pts


def _detect_large_coordinates(doc, threshold: float = 1_000_000.0) -> tuple[float, bool]:
    """Retorna maior coordenada absoluta encontrada e flag acima do limite."""
    max_abs = 0.0
    try:
        for e in doc.modelspace():
            for x, y in _entity_points(e):
                max_abs = max(max_abs, abs(x), abs(y))
    except Exception:
        pass
    return max_abs, bool(max_abs > threshold)


def _count_proxy_entities(doc) -> int:
    total = 0
    for query in ("ACAD_PROXY_ENTITY", "PROXYENTITY"):
        try:
            total += len(doc.modelspace().query(query))
        except Exception:
            continue
    return total


def _count_scales(doc) -> int:
    try:
        return len(doc.objects.query("SCALE"))
    except Exception:
        return 0


def _collect_regapps(doc) -> list[str]:
    names: list[str] = []
    try:
        for entry in doc.appids:
            name = str(getattr(entry.dxf, "name", "")).strip()
            if name:
                names.append(name)
    except Exception:
        pass
    return names


def _collect_dgn_linetypes(doc) -> list[str]:
    names: list[str] = []
    try:
        for entry in doc.linetypes:
            name = str(getattr(entry.dxf, "name", "")).strip()
            if name and any(k in name.upper() for k in _DGN_KEYWORDS):
                names.append(name)
    except Exception:
        pass
    return names


def _cleanup_regapps(doc) -> int:
    removed = 0
    for name in _collect_regapps(doc):
        if name.upper() in _REGAPP_KEEP:
            continue
        try:
            doc.appids.remove(name)
            removed += 1
        except Exception:
            continue
    return removed


def _cleanup_dgn_linetypes(doc) -> int:
    removed = 0
    for name in _collect_dgn_linetypes(doc):
        try:
            doc.linetypes.remove(name)
            removed += 1
        except Exception:
            continue
    return removed


def _parse_dxf_xref_paths(dxf_path: Path) -> tuple[list[Path], list[str]]:
    """
    Lê o DXF como pares código/valor e extrai caminhos de XREF.

    Retorna:
    - lista de caminhos resolvidos de XREF
    - lista de referências ausentes detectadas no próprio arquivo
    """
    refs: list[Path] = []
    missing: list[str] = []

    try:
        lines = dxf_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return refs, missing

    in_block = False
    block_name = ""
    block_flags = 0
    block_xref_path = ""

    def _finalize_block() -> None:
        nonlocal refs, missing, block_name, block_flags, block_xref_path
        if not (block_flags & _XREF_FLAG_BITS):
            return

        candidate: Path | None = None
        xref_raw = block_xref_path.strip().strip('"')
        if xref_raw:
            p = Path(xref_raw)
            candidate = p if p.is_absolute() else (dxf_path.parent / p)
        elif block_name and not block_name.startswith("*"):
            # fallback: alguns arquivos mantêm bloco XREF sem path explícito
            for ext in (".dxf", ".dwg"):
                c = dxf_path.parent / f"{block_name}{ext}"
                if c.exists():
                    candidate = c
                    break
            if candidate is None:
                missing.append(block_name)

        if candidate is not None:
            refs.append(candidate.resolve())
            if not candidate.exists():
                missing.append(str(candidate))

    i = 0
    while i + 1 < len(lines):
        code = lines[i].strip()
        value = lines[i + 1].strip()
        i += 2

        if code == "0" and value == "BLOCK":
            in_block = True
            block_name = ""
            block_flags = 0
            block_xref_path = ""
            continue

        if in_block:
            if code == "2":
                block_name = value
            elif code == "70":
                try:
                    block_flags = int(value)
                except Exception:
                    block_flags = 0
            elif code == "1":
                block_xref_path = value
            elif code == "0" and value == "ENDBLK":
                _finalize_block()
                in_block = False

    # DXF inconsistente sem ENDBLK final
    if in_block:
        _finalize_block()

    unique_refs: list[Path] = []
    seen: set[str] = set()
    for p in refs:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique_refs.append(p)

    unique_missing: list[str] = []
    seen_m: set[str] = set()
    for m in missing:
        key = m.lower()
        if key not in seen_m:
            seen_m.add(key)
            unique_missing.append(m)

    return unique_refs, unique_missing


def _detect_xref_cycles(root_dxf: Path, max_depth: int = 8) -> dict:
    """Monta grafo de XREFs e detecta ciclos entre arquivos DXF."""
    graph: dict[str, list[str]] = {}
    cycles: list[list[str]] = []
    missing_refs: list[str] = []
    parse_cache: dict[str, tuple[list[Path], list[str]]] = {}

    def _neighbors(path: Path) -> list[Path]:
        key = str(path.resolve())
        if key not in parse_cache:
            parse_cache[key] = _parse_dxf_xref_paths(path)
        refs, miss = parse_cache[key]
        for m in miss:
            if m not in missing_refs:
                missing_refs.append(m)
        return refs

    cycle_keys: set[tuple[str, ...]] = set()

    def _dfs(path: Path, stack: list[str]) -> None:
        cur = str(path.resolve())
        if len(stack) > max_depth:
            return

        refs = _neighbors(path)
        graph[cur] = [str(r.resolve()) for r in refs]

        for r in refs:
            nxt = str(r.resolve())
            if nxt in stack:
                idx = stack.index(nxt)
                cyc = stack[idx:] + [nxt]
                key = tuple(cyc)
                if key not in cycle_keys:
                    cycle_keys.add(key)
                    cycles.append(cyc)
                continue

            if r.exists() and r.suffix.lower() == ".dxf":
                _dfs(r, stack + [nxt])

    _dfs(root_dxf.resolve(), [str(root_dxf.resolve())])

    cycle_names: list[list[str]] = []
    for cyc in cycles:
        cycle_names.append([Path(p).name for p in cyc])

    return {
        "graph": graph,
        "cycles": cycle_names,
        "missing_refs": missing_refs,
    }


def recover_dxf(
    input_path: str,
    output_path: str | None = None,
    mode: str = "balanced",
    preview_only: bool = False,
) -> dict:
    """Executa recuperação DXF e devolve sumário estruturado.

    mode:
      - safe: apenas auditoria/diagnóstico, sem limpeza destrutiva
      - balanced: limpeza de regapps/dgn somente quando excedentes
      - aggressive: limpeza total de regapps (exceto whitelist) e DGN
    preview_only:
      - quando True, não salva arquivo de saída; retorna plano e score
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {src}")

    if src.suffix.lower() != ".dxf":
        raise ValueError("A recuperação direta suporta somente .DXF")

    mode_n = str(mode or "balanced").strip().lower()
    if mode_n not in _RECOVERY_MODES:
        mode_n = "balanced"

    out = Path(output_path) if output_path else src.with_name(f"{src.stem}_recovered.dxf")
    backup = src.with_name(f"{src.stem}_backup_before_recovery{src.suffix}")
    report_path = out.with_suffix(".recovery.json")

    if not preview_only:
        shutil.copy2(src, backup)

    doc = None
    load_mode = "readfile"
    load_errors = 0
    load_fixes = 0

    try:
        doc, aud = recover.readfile(str(src))
        load_mode = "recover.readfile"
        load_errors = len(getattr(aud, "errors", []) or [])
        load_fixes = len(getattr(aud, "fixes", []) or [])
    except Exception:
        doc = ezdxf.readfile(str(src))

    pre_regapps = _collect_regapps(doc)
    pre_dgn = _collect_dgn_linetypes(doc)
    proxy_count = _count_proxy_entities(doc)
    scale_count = _count_scales(doc)
    max_coord_abs, has_large_coords = _detect_large_coordinates(doc)
    xref_diag = _detect_xref_cycles(src)
    xref_cycles = xref_diag.get("cycles", []) or []
    xref_missing = xref_diag.get("missing_refs", []) or []

    removed_regapps = 0
    removed_dgn = 0

    should_clean_regapps = (
        mode_n == "aggressive"
        or (mode_n == "balanced" and len(pre_regapps) > 30)
    )
    should_clean_dgn = (
        mode_n in {"balanced", "aggressive"} and len(pre_dgn) > 0
    )

    if should_clean_regapps and not preview_only:
        removed_regapps = _cleanup_regapps(doc)
    elif should_clean_regapps:
        removed_regapps = max(0, len([n for n in pre_regapps if n.upper() not in _REGAPP_KEEP]))

    if should_clean_dgn and not preview_only:
        removed_dgn = _cleanup_dgn_linetypes(doc)
    elif should_clean_dgn:
        removed_dgn = len(pre_dgn)

    post_audit = doc.audit()
    post_errors = len(getattr(post_audit, "errors", []) or [])
    post_fixes = len(getattr(post_audit, "fixes", []) or [])

    if not preview_only:
        doc.saveas(str(out))

    issues: list[RecoveryIssue] = []

    if load_errors > 0:
        issues.append(RecoveryIssue(
            category="integridade",
            level="warning",
            message=f"Foram detectados {load_errors} erro(s) de leitura estrutural.",
            recommendation="Arquivo salvo novamente após recuperação e auditoria.",
        ))

    if len(pre_regapps) > 30:
        issues.append(RecoveryIssue(
            category="regapps",
            level="warning",
            message=f"RegApps em excesso detectados ({len(pre_regapps)}).",
            recommendation=(
                f"{removed_regapps} RegApps {'serão removidos' if preview_only else 'removidos'} automaticamente."
                if should_clean_regapps
                else "No modo atual não houve limpeza automática de RegApps."
            ),
        ))

    if len(pre_dgn) > 0:
        issues.append(RecoveryIssue(
            category="dgn_linetypes",
            level="warning",
            message=f"LineStyles DGN encontrados ({len(pre_dgn)}).",
            recommendation=(
                f"{removed_dgn} linetype(s) DGN {'serão removidos' if preview_only else 'removido(s)'} quando possível."
                if should_clean_dgn
                else "No modo atual não houve limpeza automática de DGN LineStyles."
            ),
        ))

    if proxy_count > 0:
        issues.append(RecoveryIssue(
            category="proxy",
            level="warning",
            message=f"Objetos proxy detectados ({proxy_count}).",
            recommendation="Instale o Object Enabler correspondente (ex.: Civil 3D) para evitar crash em seleção/REGEN.",
        ))

    if has_large_coords:
        issues.append(RecoveryIssue(
            category="coordenadas",
            level="warning",
            message=f"Coordenadas elevadas detectadas (|X|/|Y| máx ≈ {max_coord_abs:,.2f}).",
            recommendation="Considere trabalhar com origem local (mover para perto de 0,0) durante edição.",
        ))

    if scale_count > 500:
        issues.append(RecoveryIssue(
            category="scales",
            level="warning",
            message=f"Lista de escalas anotativas extensa ({scale_count}).",
            recommendation="Executar limpeza de escalas no AutoCAD (SCALELISTEDIT > Reset).",
        ))

    if xref_cycles:
        cycle_preview = " -> ".join(xref_cycles[0])
        issues.append(RecoveryIssue(
            category="xref_cycle",
            level="warning",
            message=f"Referência externa circular detectada ({len(xref_cycles)} ciclo(s)).",
            recommendation=(
                "Quebre o ciclo de XREF em pelo menos um vínculo (A não deve referenciar B se B já referencia A). "
                f"Exemplo detectado: {cycle_preview}"
            ),
        ))

    if xref_missing:
        issues.append(RecoveryIssue(
            category="xref_missing",
            level="warning",
            message=f"Referências externas ausentes ({len(xref_missing)}).",
            recommendation="Corrija os caminhos das XREFs no AutoCAD (XREF Manager) para evitar travamento no carregamento.",
        ))

    issues.append(RecoveryIssue(
        category="driver_gpu",
        level="info",
        message="Validação de driver de vídeo é dependente da máquina e não do arquivo.",
        recommendation="Atualize o driver GPU e teste com aceleração de hardware ligada/desligada no AutoCAD.",
    ))

    stats = {
        "mode": mode_n,
        "preview_only": bool(preview_only),
        "load_errors": load_errors,
        "load_fixes": load_fixes,
        "post_audit_errors": post_errors,
        "post_audit_fixes": post_fixes,
        "regapps_before": len(pre_regapps),
        "regapps_removed": removed_regapps,
        "dgn_linetypes_before": len(pre_dgn),
        "dgn_linetypes_removed": removed_dgn,
        "proxy_entities": proxy_count,
        "annotative_scales": scale_count,
        "max_abs_coord": max_coord_abs,
        "xref_cycles": len(xref_cycles),
        "xref_missing": len(xref_missing),
    }
    health_score = _compute_health_score(stats)

    planned_actions = [
        {
            "action": "audit_and_resave",
            "enabled": True,
            "estimated_items": max(load_errors, post_fixes),
            "description": "Executar auditoria estrutural e normalização interna do DXF.",
        },
        {
            "action": "remove_regapps",
            "enabled": bool(should_clean_regapps),
            "estimated_items": int(removed_regapps),
            "description": "Limpeza de RegApps excedentes para reduzir sobrecarga e instabilidade.",
        },
        {
            "action": "remove_dgn_linetypes",
            "enabled": bool(should_clean_dgn),
            "estimated_items": int(removed_dgn),
            "description": "Remoção de linetypes DGN/MicroStation quando detectados.",
        },
        {
            "action": "diagnose_xref",
            "enabled": True,
            "estimated_items": int(len(xref_cycles) + len(xref_missing)),
            "description": "Diagnóstico de ciclo de XREF e referências ausentes.",
        },
    ]

    result = {
        "input": str(src),
        "backup": str(backup) if not preview_only else "",
        "output": str(out),
        "report": str(report_path) if not preview_only else "",
        "mode": mode_n,
        "preview_only": bool(preview_only),
        "load_mode": load_mode,
        "load_errors": load_errors,
        "load_fixes": load_fixes,
        "post_audit_errors": post_errors,
        "post_audit_fixes": post_fixes,
        "health_score": health_score,
        "stats": stats,
        "xref_cycles": xref_cycles,
        "xref_missing_refs": xref_missing,
        "xref_graph": xref_diag.get("graph", {}),
        "planned_actions": planned_actions,
        "issues": [asdict(i) for i in issues],
    }

    if not preview_only:
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def recover_folder(
    folder_path: str,
    recursive: bool = True,
    mode: str = "balanced",
    include_dwg: bool = False,
    preview_only: bool = False,
) -> dict:
    """Executa recuperação em lote para uma pasta e retorna sumário."""
    root = Path(folder_path)
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"Pasta inválida: {root}")

    pattern = "**/*" if recursive else "*"
    files: list[Path] = []
    for p in root.glob(pattern):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext == ".dxf" or (include_dwg and ext == ".dwg"):
            files.append(p)

    files = sorted(files)
    rows: list[dict[str, Any]] = []
    ok = 0
    fail = 0
    planned_regapps = 0
    planned_dgn = 0
    planned_xref_issues = 0

    for fp in files:
        try:
            if fp.suffix.lower() != ".dxf":
                rows.append({
                    "file": str(fp),
                    "status": "skipped",
                    "reason": "DWG direto não suportado em recover_folder()",
                })
                continue

            out = fp.with_name(f"{fp.stem}_recovered.dxf")
            info = recover_dxf(str(fp), str(out), mode=mode, preview_only=preview_only)
            stats = info.get("stats", {}) if isinstance(info, dict) else {}
            planned_regapps += int(stats.get("regapps_removed", 0) or 0)
            planned_dgn += int(stats.get("dgn_linetypes_removed", 0) or 0)
            planned_xref_issues += int(stats.get("xref_cycles", 0) or 0) + int(stats.get("xref_missing", 0) or 0)
            rows.append({
                "file": str(fp),
                "status": "preview" if preview_only else "ok",
                "output": info.get("output", ""),
                "report": info.get("report", ""),
                "health_score": info.get("health_score", 0),
                "issues": len(info.get("issues", []) or []),
            })
            ok += 1
        except Exception as exc:
            rows.append({
                "file": str(fp),
                "status": "error",
                "error": str(exc),
            })
            fail += 1

    out_json = root / f"recovery_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary = {
        "folder": str(root.resolve()),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "preview_only": bool(preview_only),
        "recursive": bool(recursive),
        "total": len(files),
        "ok": ok,
        "fail": fail,
        "planned": {
            "regapps_removed": planned_regapps,
            "dgn_linetypes_removed": planned_dgn,
            "xref_issues": planned_xref_issues,
        },
        "items": rows,
        "summary_file": str(out_json.resolve()) if not preview_only else "",
    }
    if not preview_only:
        out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
