"""Anotação de DXF: salva uma cópia do arquivo com a layer _QC_ISSUES contendo
MText próximo a cada entidade problemática encontrada pela verificação.

O projetista abre o arquivo anotado no AutoCAD e vê os problemas marcados
diretamente no desenho.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import ezdxf

_QC_LAYER = "_QC_ISSUES"
_QC_COLOR  = 1   # vermelho ACI


def annotate_dxf(result: Dict, output_path: str | None = None) -> str:
    """Salva cópia anotada do DXF com issues marcadas na layer _QC_ISSUES.

    Parameters
    ----------
    result:       dicionário retornado por DXFChecker.check()
    output_path:  caminho do arquivo de saída
                  (padrão: <pasta_original>/<stem>_annotated.dxf)

    Returns
    -------
    str — caminho absoluto do arquivo gerado
    """
    src = Path(result["file_path"])
    if output_path is None:
        output_path = str(src.parent / (src.stem + "_annotated.dxf"))

    # ── Abrir o documento original ────────────────────────────────────────────
    try:
        doc = ezdxf.readfile(str(src))
    except Exception:
        import ezdxf.recover as _rec
        doc, _ = _rec.readfile(str(src))

    # ── Garantir layer _QC_ISSUES ─────────────────────────────────────────────
    if _QC_LAYER not in doc.layers:
        lyr = doc.layers.add(_QC_LAYER)
    else:
        lyr = doc.layers.get(_QC_LAYER)
    lyr.color = _QC_COLOR

    msp = doc.modelspace()

    # ── Estimar altura de texto com base no bbox do desenho ───────────────────
    bbox   = result.get("geo_bbox") or {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}
    span_x = abs(bbox.get("maxX", 100) - bbox.get("minX", 0))
    span_y = abs(bbox.get("maxY", 100) - bbox.get("minY", 0))
    span   = max(span_x, span_y, 1.0)
    text_h = max(span / 120.0, 0.5)
    offset = text_h * 1.5

    # ── Mapa handle → posição (extraído da geometria já calculada) ────────────
    handle_to_pos: dict[str, tuple[float, float]] = {}
    for shape in result.get("geometry", []):
        h = shape.get("handle", "")
        if not h:
            continue
        if "x1" in shape and "y1" in shape:
            handle_to_pos[h] = (
                (shape["x1"] + shape["x2"]) / 2,
                (shape["y1"] + shape["y2"]) / 2,
            )
        elif "cx" in shape:
            handle_to_pos[h] = (shape["cx"], shape["cy"])
        elif "x" in shape:
            handle_to_pos[h] = (shape["x"], shape["y"])
        elif "points" in shape and shape["points"]:
            pts = shape["points"]
            handle_to_pos[h] = (
                sum(p[0] for p in pts) / len(pts),
                sum(p[1] for p in pts) / len(pts),
            )

    # ── Inserir MText por issue ───────────────────────────────────────────────
    SEV_PREFIX = {"ERROR": "[ERRO]", "WARNING": "[AVISO]", "INFO": "[INFO]"}
    annotated = 0

    for issue in result["issues"]:
        pos = handle_to_pos.get(issue.handle or "")
        if pos is None:
            continue

        prefix = SEV_PREFIX.get(issue.severity.value, "[?]")
        label  = (
            f"{prefix} {issue.rule}\\P"
            f"{issue.message[:80]}"
        )

        try:
            msp.add_mtext(
                label,
                dxfattribs={
                    "layer":       _QC_LAYER,
                    "insert":      (pos[0], pos[1] + offset),
                    "char_height": text_h,
                    "color":       _QC_COLOR,
                    "width":       text_h * 40,
                },
            )
            annotated += 1
        except Exception:
            continue

    # ── Issues sem handle: bloco de resumo no canto superior esquerdo ─────────
    no_pos = [i for i in result["issues"] if not handle_to_pos.get(i.handle or "")]
    if no_pos:
        sx = bbox.get("minX", 0)
        sy = bbox.get("maxY", 100) + text_h * 4
        lines = [f"DWG QC — {len(no_pos)} ocorrência(s) sem posição definida:"]
        for iss in no_pos[:12]:
            lines.append(
                f"  [{iss.severity.value}] {iss.rule}: {iss.message[:60]}"
            )
        if len(no_pos) > 12:
            lines.append(f"  … e mais {len(no_pos) - 12}")
        try:
            msp.add_mtext(
                "\\P".join(lines),
                dxfattribs={
                    "layer":       _QC_LAYER,
                    "insert":      (sx, sy),
                    "char_height": text_h,
                    "color":       _QC_COLOR,
                    "width":       text_h * 60,
                },
            )
        except Exception:
            pass

    doc.saveas(str(output_path))
    return str(output_path)
