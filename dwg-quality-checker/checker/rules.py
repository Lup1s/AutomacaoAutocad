"""
Módulo de regras de verificação para arquivos DXF/DWG.

Cada função recebe o documento ezdxf e o dicionário de configuração,
e retorna uma lista de Issues encontrados.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List

import ezdxf


# ─────────────────────────────────────────────────────────────────────────────
#  Severidade e Issue
# ─────────────────────────────────────────────────────────────────────────────


class Severity(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Issue:
    rule: str
    severity: Severity
    message: str
    entity_type: str = ""
    layer: str = ""
    handle: str = ""
    location: str = ""   # coordenadas da entidade — "X:100.50  Y:203.10"
    details: str = ""


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: extração de coordenadas
# ─────────────────────────────────────────────────────────────────────────────


def _coord(entity) -> str:
    """Extrai coordenadas de inserção/início de uma entidade DXF."""
    try:
        for attr in ("insert", "start", "center", "location"):
            if entity.dxf.hasattr(attr):
                pt = entity.dxf.get(attr)
                return f"X:{float(pt[0]):.2f}  Y:{float(pt[1]):.2f}"
        if entity.dxftype() == "LWPOLYLINE":
            pts = list(entity.vertices())
            if pts:
                return f"X:{float(pts[0][0]):.2f}  Y:{float(pts[0][1]):.2f}"
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────────────────────
#  Regras de Layer
# ─────────────────────────────────────────────────────────────────────────────


def check_required_layers(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica se as layers obrigatórias estão presentes."""
    required: list[str] = config.get("layers", {}).get("required", [])
    existing = {layer.dxf.name for layer in doc.layers}

    return [
        Issue(
            rule="REQUIRED_LAYER_MISSING",
            severity=Severity.ERROR,
            message=f"Layer obrigatória '{name}' não encontrada no desenho",
            entity_type="LAYER",
            layer=name,
        )
        for name in required
        if name not in existing
    ]


def check_entities_on_layer_zero(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica entidades desenhadas diretamente na layer '0'."""
    if not config.get("drawing", {}).get("check_entities_on_layer_0", True):
        return []

    msp = doc.modelspace()
    entities = [e for e in msp if e.dxf.layer == "0"]

    if not entities:
        return []

    MAX = 25
    issues: List[Issue] = []
    for entity in entities[:MAX]:
        issues.append(Issue(
            rule="ENTITIES_ON_LAYER_0",
            severity=Severity.WARNING,
            message=f"Entidade '{entity.dxftype()}' na layer '0' — use uma layer nomeada",
            entity_type=entity.dxftype(),
            layer="0",
            handle=entity.dxf.get("handle", ""),
            location=_coord(entity),
        ))

    if len(entities) > MAX:
        issues.append(Issue(
            rule="ENTITIES_ON_LAYER_0",
            severity=Severity.WARNING,
            message=f"... e mais {len(entities) - MAX} entidade(s) na layer '0' (total: {len(entities)})",
            entity_type="MULTIPLE",
            layer="0",
            details=f"Exibindo {MAX} de {len(entities)} ocorrências",
        ))

    return issues


def check_frozen_layers_with_entities(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica layers congeladas que ainda possuem entidades."""
    if not config.get("drawing", {}).get("check_frozen_layers", True):
        return []

    frozen = {layer.dxf.name for layer in doc.layers if layer.is_frozen()}
    if not frozen:
        return []

    msp = doc.modelspace()
    counts: dict[str, int] = {}
    first_loc: dict[str, str] = {}
    etypes: dict[str, set] = {}
    for entity in msp:
        lyr = entity.dxf.layer
        if lyr in frozen:
            counts[lyr] = counts.get(lyr, 0) + 1
            if lyr not in first_loc:
                first_loc[lyr] = _coord(entity)
            etypes.setdefault(lyr, set()).add(entity.dxftype())

    return [
        Issue(
            rule="ENTITIES_ON_FROZEN_LAYER",
            severity=Severity.WARNING,
            message=f"Layer '{lyr}' está CONGELADA mas contém {n} entidade(s)",
            entity_type=", ".join(sorted(etypes.get(lyr, set()))),
            layer=lyr,
            location=first_loc.get(lyr, ""),
            details=f"Tipos: {', '.join(sorted(etypes.get(lyr, set())))}",
        )
        for lyr, n in counts.items()
    ]


def check_off_layers_with_entities(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica layers desligadas que ainda possuem entidades."""
    if not config.get("drawing", {}).get("check_off_layers", True):
        return []

    off = {layer.dxf.name for layer in doc.layers if not layer.is_on()}
    if not off:
        return []

    msp = doc.modelspace()
    counts: dict[str, int] = {}
    first_loc: dict[str, str] = {}
    etypes: dict[str, set] = {}
    for entity in msp:
        lyr = entity.dxf.layer
        if lyr in off:
            counts[lyr] = counts.get(lyr, 0) + 1
            if lyr not in first_loc:
                first_loc[lyr] = _coord(entity)
            etypes.setdefault(lyr, set()).add(entity.dxftype())

    return [
        Issue(
            rule="ENTITIES_ON_OFF_LAYER",
            severity=Severity.INFO,
            message=f"Layer '{lyr}' está DESLIGADA mas contém {n} entidade(s)",
            entity_type=", ".join(sorted(etypes.get(lyr, set()))),
            layer=lyr,
            location=first_loc.get(lyr, ""),
            details=f"Tipos: {', '.join(sorted(etypes.get(lyr, set())))}",
        )
        for lyr, n in counts.items()
    ]


def check_empty_layers(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica layers definidas sem nenhuma entidade no model space."""
    if not config.get("drawing", {}).get("check_empty_layers", True):
        return []

    msp = doc.modelspace()
    used = {e.dxf.layer for e in msp}
    skip = {"0", "Defpoints", "DEFPOINTS"}

    empty = sorted(
        layer.dxf.name
        for layer in doc.layers
        if layer.dxf.name not in used and layer.dxf.name not in skip
    )

    if not empty:
        return []

    return [
        Issue(
            rule="EMPTY_LAYERS",
            severity=Severity.INFO,
            message=f"{len(empty)} layer(s) definida(s) sem entidades no model space",
            entity_type="LAYER",
            details=", ".join(empty),
        )
    ]


def check_layer_naming_convention(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica se os nomes das layers seguem uma convenção definida por regex."""
    convention: str = config.get("layers", {}).get("naming_convention", "")
    if not convention:
        return []

    MAX     = 50
    pattern = re.compile(convention)
    skip    = {"0", "Defpoints", "DEFPOINTS"}
    bad     = [
        layer for layer in doc.layers
        if layer.dxf.name not in skip and not pattern.match(layer.dxf.name)
    ]
    issues  = [
        Issue(
            rule="LAYER_NAMING_CONVENTION",
            severity=Severity.WARNING,
            message=f"Layer '{layer.dxf.name}' não segue a convenção '{convention}'",
            entity_type="LAYER",
            layer=layer.dxf.name,
        )
        for layer in bad[:MAX]
    ]
    if len(bad) > MAX:
        issues.append(Issue(
            rule="LAYER_NAMING_CONVENTION",
            severity=Severity.WARNING,
            message=f"... e mais {len(bad) - MAX} layer(s) com nome inválido (total: {len(bad)})",
            entity_type="MULTIPLE",
            details=f"Exibindo {MAX} de {len(bad)} ocorrências",
        ))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
#  Regras de Texto
# ─────────────────────────────────────────────────────────────────────────────


def check_text_heights(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica se as alturas dos textos estão dentro do intervalo permitido."""
    text_cfg = config.get("text", {})
    min_h = float(text_cfg.get("min_height", 1.5))
    max_h = float(text_cfg.get("max_height", 10.0))

    MAX    = 25
    issues: List[Issue] = []
    total  = 0
    for entity in doc.modelspace():
        if entity.dxftype() not in ("TEXT", "MTEXT"):
            continue
        # MTEXT usa char_height; TEXT usa height
        attr   = "char_height" if entity.dxftype() == "MTEXT" else "height"
        height = entity.dxf.get(attr, 0)
        if height == 0:
            continue  # herda do estilo — ignorar
        if height < min_h or height > max_h:
            total += 1
            if len(issues) < MAX:
                issues.append(Issue(
                    rule="TEXT_HEIGHT_OUT_OF_RANGE",
                    severity=Severity.WARNING,
                    message=(
                        f"Texto com altura {height:.3g} "
                        f"fora do intervalo [{min_h}, {max_h}]"
                    ),
                    entity_type=entity.dxftype(),
                    layer=entity.dxf.layer,
                    handle=entity.dxf.get("handle", ""),
                    location=_coord(entity),
                    details=f"Altura atual: {height:.3g}",
                ))
    if total > MAX:
        issues.append(Issue(
            rule="TEXT_HEIGHT_OUT_OF_RANGE",
            severity=Severity.WARNING,
            message=f"... e mais {total - MAX} texto(s) com altura fora do intervalo (total: {total})",
            entity_type="MULTIPLE",
            details=f"Exibindo {MAX} de {total} ocorrências",
        ))
    return issues


# ─────────────────────────────────────────────────────────────────────────────
#  Regras de Bloco
# ─────────────────────────────────────────────────────────────────────────────


def check_unused_blocks(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica blocos definidos mas não inseridos no model space."""
    if not config.get("drawing", {}).get("check_unused_blocks", True):
        return []

    msp = doc.modelspace()
    used = {e.dxf.name for e in msp if e.dxftype() == "INSERT"}
    defined = {
        block.name
        for block in doc.blocks
        if not block.name.startswith("*")  # ignora *Model_Space, *Paper_Space, etc.
    }

    unused = sorted(defined - used)
    if not unused:
        return []

    return [
        Issue(
            rule="UNUSED_BLOCK_DEFINITIONS",
            severity=Severity.INFO,
            message=(
                f"{len(unused)} bloco(s) definido(s) mas não inserido(s) — "
                "considere executar PURGE"
            ),
            entity_type="BLOCK",
            details=", ".join(unused),
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  Regras de Padrão — Cor, Tipo de Linha, Duplicatas e XREFs
# ─────────────────────────────────────────────────────────────────────────────


def check_color_not_bylayer(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica entidades com cor explícita em vez de BYLAYER."""
    if not config.get("drawing", {}).get("check_color_bylayer", True):
        return []

    BYLAYER = 256
    SKIP = {"VIEWPORT", "ATTDEF", "DIMENSION", "LEADER", "MULTILEADER",
            "HATCH", "WIPEOUT", "XLINE"}
    MAX = 25
    issues: List[Issue] = []
    total = 0

    for entity in doc.modelspace():
        if entity.dxftype() in SKIP:
            continue
        if not entity.dxf.hasattr("color"):
            continue
        color = entity.dxf.color
        if color == BYLAYER:
            continue
        total += 1
        if len(issues) < MAX:
            label = "ByBlock" if color == 0 else f"ACI {color}"
            issues.append(Issue(
                rule="COLOR_NOT_BYLAYER",
                severity=Severity.WARNING,
                message=f"'{entity.dxftype()}' com cor explícita ({label}) na layer '{entity.dxf.layer}'",
                entity_type=entity.dxftype(),
                layer=entity.dxf.layer,
                handle=entity.dxf.get("handle", ""),
                location=_coord(entity),
                details=f"Cor ACI: {color}",
            ))

    if total > MAX:
        issues.append(Issue(
            rule="COLOR_NOT_BYLAYER",
            severity=Severity.WARNING,
            message=f"... e mais {total - MAX} entidade(s) com cor explícita (total: {total})",
            entity_type="MULTIPLE",
            details=f"Exibindo {MAX} de {total} ocorrências",
        ))
    return issues


def check_linetype_not_bylayer(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Verifica entidades com tipo de linha explícito em vez de BYLAYER."""
    if not config.get("drawing", {}).get("check_linetype_bylayer", True):
        return []

    SKIP    = {"VIEWPORT", "ATTDEF", "DIMENSION", "LEADER", "MULTILEADER",
               "HATCH", "WIPEOUT", "XLINE"}
    ALLOWED = {"BYLAYER", "BYBLOCK", ""}
    MAX = 25
    issues: List[Issue] = []
    total = 0

    for entity in doc.modelspace():
        if entity.dxftype() in SKIP:
            continue
        if not entity.dxf.hasattr("linetype"):
            continue
        lt = entity.dxf.linetype
        if lt.upper() in ALLOWED:
            continue
        total += 1
        if len(issues) < MAX:
            issues.append(Issue(
                rule="LINETYPE_NOT_BYLAYER",
                severity=Severity.WARNING,
                message=f"'{entity.dxftype()}' com tipo de linha explícito ('{lt}') na layer '{entity.dxf.layer}'",
                entity_type=entity.dxftype(),
                layer=entity.dxf.layer,
                handle=entity.dxf.get("handle", ""),
                location=_coord(entity),
                details=f"Tipo de linha: {lt}",
            ))

    if total > MAX:
        issues.append(Issue(
            rule="LINETYPE_NOT_BYLAYER",
            severity=Severity.WARNING,
            message=f"... e mais {total - MAX} entidade(s) com tipo de linha explícito (total: {total})",
            entity_type="MULTIPLE",
            details=f"Exibindo {MAX} de {total} ocorrências",
        ))
    return issues


def check_duplicate_entities(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Detecta entidades duplicadas/sobrepostas no mesmo layer e posição."""
    if not config.get("drawing", {}).get("check_duplicates", True):
        return []

    SKIP = {"VIEWPORT", "ATTDEF", "HATCH", "DIMENSION", "LEADER",
            "MULTILEADER", "WIPEOUT", "XLINE"}
    TOL  = 2   # casas decimais para arredondamento de coordenadas
    seen: dict = {}   # fingerprint → handle da primeira ocorrência
    dups: list = []   # lista de (entidade_dup, handle_original)
    MAX  = 25

    def _fp(entity) -> tuple | None:
        t   = entity.dxftype()
        lay = entity.dxf.layer
        try:
            if t == "LINE":
                s, e2 = entity.dxf.start, entity.dxf.end
                return (t, lay,
                        round(s.x, TOL), round(s.y, TOL),
                        round(e2.x, TOL), round(e2.y, TOL))
            if t == "CIRCLE":
                c = entity.dxf.center
                return (t, lay, round(c.x, TOL), round(c.y, TOL),
                        round(entity.dxf.radius, TOL))
            if t == "ARC":
                c = entity.dxf.center
                return (t, lay, round(c.x, TOL), round(c.y, TOL),
                        round(entity.dxf.radius, TOL),
                        round(entity.dxf.start_angle, 1),
                        round(entity.dxf.end_angle,   1))
            if t in ("TEXT", "MTEXT"):
                ins  = entity.dxf.insert
                text = entity.dxf.get("text", "")
                return (t, lay, round(ins.x, TOL), round(ins.y, TOL),
                        str(text)[:40])
            if t == "INSERT":
                ins = entity.dxf.insert
                return (t, lay, entity.dxf.name,
                        round(ins.x, TOL), round(ins.y, TOL))
            if t == "LWPOLYLINE":
                pts = [(round(float(x), TOL), round(float(y), TOL))
                       for x, y, *_ in entity.get_points()]
                if pts:
                    return (t, lay, len(pts), pts[0], pts[-1])
        except Exception:
            pass
        return None

    for entity in doc.modelspace():
        if entity.dxftype() in SKIP:
            continue
        fp = _fp(entity)
        if fp is None:
            continue
        handle = entity.dxf.get("handle", "")
        if fp in seen:
            dups.append((entity, seen[fp]))
        else:
            seen[fp] = handle

    if not dups:
        return []

    issues: List[Issue] = []
    for entity, orig in dups[:MAX]:
        issues.append(Issue(
            rule="DUPLICATE_ENTITIES",
            severity=Severity.ERROR,
            message=f"Entidade '{entity.dxftype()}' duplicada na layer '{entity.dxf.layer}'",
            entity_type=entity.dxftype(),
            layer=entity.dxf.layer,
            handle=entity.dxf.get("handle", ""),
            location=_coord(entity),
            details=f"Duplicata do handle #{orig}",
        ))
    if len(dups) > MAX:
        issues.append(Issue(
            rule="DUPLICATE_ENTITIES",
            severity=Severity.ERROR,
            message=f"... e mais {len(dups) - MAX} entidade(s) duplicada(s) (total: {len(dups)})",
            entity_type="MULTIPLE",
            details=f"Exibindo {MAX} de {len(dups)} duplicatas",
        ))
    return issues


def check_xrefs(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    """Detecta referências externas (XREFs) e verifica se estão carregadas."""
    if not config.get("drawing", {}).get("check_xrefs", True):
        return []

    BLK_XREF         = 4
    BLK_XREF_OVERLAY = 8
    issues: List[Issue] = []

    for block_layout in doc.blocks:
        name = block_layout.name
        if name.startswith("*"):
            continue
        try:
            block_entity = block_layout.block
            flags = block_entity.dxf.get("flags", 0)
            if not (flags & BLK_XREF or flags & BLK_XREF_OVERLAY):
                continue
            xref_path = block_entity.dxf.get("xref_path", name)
            xref_type = "OVERLAY" if (flags & BLK_XREF_OVERLAY) else "ATTACH"

            # Conta entidades reais (exclui marcadores BLOCK/ENDBLK)
            ent_count = sum(
                1 for e in block_layout
                if e.dxftype() not in ("BLOCK", "ENDBLK")
            )
            loaded = ent_count > 0

            # Verifica se o arquivo existe no disco
            file_exists = bool(xref_path) and os.path.isfile(xref_path)
            path_note   = "" if file_exists or not xref_path else " (arquivo não encontrado no disco)"

            issues.append(Issue(
                rule="XREF_NOT_LOADED" if not loaded else "XREF_DETECTED",
                severity=Severity.ERROR if not loaded else Severity.INFO,
                message=(
                    f"XREF '{name}' não carregada{path_note} — verificar dependência"
                    if not loaded else
                    f"XREF '{name}' detectada e carregada ({ent_count} entidades)"
                ),
                entity_type=f"XREF_{xref_type}",
                details=f"Arquivo: {xref_path or '(caminho não definido)'}",
            ))
        except Exception:
            pass

    return issues


# ─────────────────────────────────────────────────────────────────────────────
#  Registro de Regras
# ─────────────────────────────────────────────────────────────────────────────


def get_all_rules() -> List[Callable]:
    """Retorna a lista de todas as funções de regra disponíveis."""
    return [
        check_required_layers,
        check_entities_on_layer_zero,
        check_frozen_layers_with_entities,
        check_off_layers_with_entities,
        check_empty_layers,
        check_layer_naming_convention,
        check_text_heights,
        check_unused_blocks,
        check_color_not_bylayer,
        check_linetype_not_bylayer,
        check_duplicate_entities,
        check_xrefs,
    ]
