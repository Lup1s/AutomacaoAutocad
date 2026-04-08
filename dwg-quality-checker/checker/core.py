"""
Núcleo do verificador: carrega a configuração YAML e executa todas as regras
sobre um arquivo DXF/DWG, retornando um dicionário de resultados.
"""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import hashlib

import ezdxf
import yaml

from .rules import Issue, Severity, get_all_rules


def _find_default_config() -> Path:
    """Resolve config.yaml tanto no desenvolvimento quanto no executável."""
    if getattr(sys, 'frozen', False):
        # Instalado: verifica primeiro ao lado do .exe (editável pelo usuário)
        exe_dir = Path(sys.executable).parent
        user_cfg = exe_dir / "config.yaml"
        if user_cfg.exists():
            return user_cfg
        return Path(sys._MEIPASS) / "config.yaml"
    return Path(__file__).parent.parent / "config.yaml"


DEFAULT_CONFIG = _find_default_config()


# ── Config defaults & validation ──────────────────────────────────────────────

_CONFIG_DEFAULTS: dict = {
    "layers":  {"required": [], "naming_convention": ""},
    "text":    {"min_height": 0.03, "max_height": 50.0},
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
        # Novas regras v2.5
        "check_title_block":         True,
        "check_viewport":            True,
        "check_mtext_overflow":      True,
        "check_external_fonts":      True,
        "check_line_weights":        True,
        "check_plot_styles":         True,
    },
}


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on", "sim", "s"}:
            return True
        if v in {"0", "false", "no", "n", "off", "nao", "não"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            s = item.strip()
            if s:
                out.append(s)
    return out


def _validate_config(cfg: dict) -> dict:
    """Normaliza configuração do usuário para execução resiliente."""
    if not isinstance(cfg, dict):
        cfg = {}

    for section, defaults in _CONFIG_DEFAULTS.items():
        if not isinstance(cfg.get(section), dict):
            cfg[section] = dict(defaults)
        else:
            for key, val in defaults.items():
                cfg[section].setdefault(key, val)

    # layers
    cfg["layers"]["required"] = _as_str_list(cfg["layers"].get("required"))
    naming = cfg["layers"].get("naming_convention", "")
    cfg["layers"]["naming_convention"] = naming if isinstance(naming, str) else ""

    # text
    min_h = _as_float(cfg["text"].get("min_height"), _CONFIG_DEFAULTS["text"]["min_height"])
    max_h = _as_float(cfg["text"].get("max_height"), _CONFIG_DEFAULTS["text"]["max_height"])
    if min_h > max_h:
        min_h, max_h = max_h, min_h
    cfg["text"]["min_height"] = min_h
    cfg["text"]["max_height"] = max_h

    # drawing flags
    for key, default in _CONFIG_DEFAULTS["drawing"].items():
        cfg["drawing"][key] = _as_bool(cfg["drawing"].get(key), default)

    # rules severity overrides
    rules = cfg.get("rules")
    if not isinstance(rules, dict):
        rules = {}
    sev = rules.get("severity_overrides")
    normalized: dict[str, str] = {}
    if isinstance(sev, dict):
        for rule_name, severity in sev.items():
            if not isinstance(rule_name, str):
                continue
            if not isinstance(severity, str):
                continue
            sev_u = severity.strip().upper()
            if sev_u in {"ERROR", "WARNING", "INFO"}:
                normalized[rule_name.strip()] = sev_u
    rules["severity_overrides"] = normalized
    cfg["rules"] = rules

    return cfg


def _normalize_profile_overrides(profile_cfg: dict) -> dict:
    """Normaliza um perfil parcial sem forçar defaults em seções ausentes."""
    if not isinstance(profile_cfg, dict):
        return {}

    out: dict = {}

    layers = profile_cfg.get("layers")
    if isinstance(layers, dict):
        layer_out: dict = {}
        if "required" in layers:
            layer_out["required"] = _as_str_list(layers.get("required"))
        if "naming_convention" in layers:
            naming = layers.get("naming_convention", "")
            layer_out["naming_convention"] = naming if isinstance(naming, str) else ""
        if layer_out:
            out["layers"] = layer_out

    text = profile_cfg.get("text")
    if isinstance(text, dict):
        text_out: dict = {}
        if "min_height" in text:
            text_out["min_height"] = _as_float(text.get("min_height"), _CONFIG_DEFAULTS["text"]["min_height"])
        if "max_height" in text:
            text_out["max_height"] = _as_float(text.get("max_height"), _CONFIG_DEFAULTS["text"]["max_height"])
        if "min_height" in text_out and "max_height" in text_out and text_out["min_height"] > text_out["max_height"]:
            text_out["min_height"], text_out["max_height"] = text_out["max_height"], text_out["min_height"]
        if text_out:
            out["text"] = text_out

    drawing = profile_cfg.get("drawing")
    if isinstance(drawing, dict):
        draw_out: dict = {}
        for key, default in _CONFIG_DEFAULTS["drawing"].items():
            if key in drawing:
                draw_out[key] = _as_bool(drawing.get(key), default)
        if draw_out:
            out["drawing"] = draw_out

    rules = profile_cfg.get("rules")
    if isinstance(rules, dict) and "severity_overrides" in rules:
        sev = rules.get("severity_overrides")
        normalized: dict[str, str] = {}
        if isinstance(sev, dict):
            for rule_name, severity in sev.items():
                if not isinstance(rule_name, str) or not isinstance(severity, str):
                    continue
                sev_u = severity.strip().upper()
                if sev_u in {"ERROR", "WARNING", "INFO"}:
                    normalized[rule_name.strip()] = sev_u
        out["rules"] = {"severity_overrides": normalized}

    return out


def merge_profile_into_config(base_cfg: dict, profile_cfg: dict) -> dict:
    """Aplica overrides de perfil sobre uma configuração base normalizada."""
    merged = _validate_config(copy.deepcopy(base_cfg) if isinstance(base_cfg, dict) else {})
    overrides = _normalize_profile_overrides(profile_cfg)

    if "layers" in overrides:
        merged.setdefault("layers", {}).update(overrides["layers"])

    if "text" in overrides:
        merged.setdefault("text", {}).update(overrides["text"])
        min_h = _as_float(merged["text"].get("min_height"), _CONFIG_DEFAULTS["text"]["min_height"])
        max_h = _as_float(merged["text"].get("max_height"), _CONFIG_DEFAULTS["text"]["max_height"])
        if min_h > max_h:
            min_h, max_h = max_h, min_h
        merged["text"]["min_height"] = min_h
        merged["text"]["max_height"] = max_h

    if "drawing" in overrides:
        merged.setdefault("drawing", {}).update(overrides["drawing"])

    if "rules" in overrides:
        merged.setdefault("rules", {})
        merged["rules"]["severity_overrides"] = overrides["rules"]["severity_overrides"]

    return merged


def merge_profiles_into_config(base_cfg: dict, profile_cfg_list: list[dict]) -> dict:
    """Aplica múltiplos perfis em sequência sobre uma configuração base."""
    merged = _validate_config(copy.deepcopy(base_cfg) if isinstance(base_cfg, dict) else {})
    if not isinstance(profile_cfg_list, list):
        return merged

    for profile_cfg in profile_cfg_list:
        if not isinstance(profile_cfg, dict):
            continue
        merged = merge_profile_into_config(merged, profile_cfg)
    return merged


# ── Geometry extractor ────────────────────────────────────────────────────────

def _extract_geometry(doc, issue_handles: set = None, max_shapes: int = 1500) -> dict:
    """
    Extrai geometria simples do modelspace para renderização SVG.

    - issue_handles: handles das entidades com problemas (sempre incluídas)
    - max_shapes:    limite de entidades não-problemáticas após filtragem
    - Retorna dict com 'shapes' (list) e 'bbox' (dict minX/minY/maxX/maxY)
    """
    issue_handles = issue_handles or set()
    all_shapes: list = []

    for e in doc.modelspace():
        t = e.dxftype()
        try:
            base = {
                "type":   t,
                "layer":  e.dxf.layer,
                "handle": e.dxf.handle,
            }
            shape = None
            if t == "LINE":
                s, nd = e.dxf.start, e.dxf.end
                shape = {**base,
                    "x1": round(float(s.x), 4), "y1": round(float(s.y), 4),
                    "x2": round(float(nd.x), 4), "y2": round(float(nd.y), 4)}
            elif t == "CIRCLE":
                c = e.dxf.center
                shape = {**base,
                    "cx": round(float(c.x), 4), "cy": round(float(c.y), 4),
                    "r":  round(float(e.dxf.radius), 4)}
            elif t == "ARC":
                c = e.dxf.center
                shape = {**base,
                    "cx": round(float(c.x), 4), "cy": round(float(c.y), 4),
                    "r":  round(float(e.dxf.radius), 4),
                    "start_angle": round(float(e.dxf.start_angle), 2),
                    "end_angle":   round(float(e.dxf.end_angle), 2)}
            elif t in ("TEXT", "MTEXT"):
                p = e.dxf.insert
                text = e.dxf.get("text", "") if t == "TEXT" else e.text[:60]
                shape = {**base,
                    "x": round(float(p.x), 4), "y": round(float(p.y), 4),
                    "height": round(float(e.dxf.get("height", 2.5)), 4),
                    "text":   str(text)[:60]}
            elif t == "LWPOLYLINE":
                pts = [[round(float(x), 4), round(float(y), 4)]
                       for x, y, *_ in e.get_points()]
                shape = {**base, "points": pts, "closed": bool(e.closed)}
            elif t == "POLYLINE":
                pts = [[round(float(v.dxf.location.x), 4),
                        round(float(v.dxf.location.y), 4)]
                       for v in e.vertices]
                shape = {**base, "points": pts, "closed": False}
            elif t == "INSERT":
                p = e.dxf.insert
                shape = {**base,
                    "x": round(float(p.x), 4), "y": round(float(p.y), 4),
                    "name": e.dxf.name,
                    "sx":   round(float(e.dxf.get("xscale", 1)), 4),
                    "sy":   round(float(e.dxf.get("yscale", 1)), 4)}
            elif t == "SPLINE":
                pts = [[round(float(p.x), 4), round(float(p.y), 4)]
                       for p in e.control_points]
                shape = {**base, "points": pts, "closed": False}
            if shape:
                all_shapes.append(shape)
        except Exception:
            pass  # entidade sem geometria acessível — ignorar

    if not all_shapes:
        return {"shapes": [], "bbox": {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}}

    # ── Bounding box com percentil para excluir entidades soltas em 0,0 ───────
    all_x: list = []
    all_y: list = []

    def _collect(g: dict) -> None:
        if "x1" in g:
            all_x.extend([g["x1"], g["x2"]]); all_y.extend([g["y1"], g["y2"]])
        elif "cx" in g:
            all_x.append(g["cx"]); all_y.append(g["cy"])
        elif "x" in g:
            all_x.append(g["x"]); all_y.append(g["y"])
        elif "points" in g:
            for p in g["points"]:
                all_x.append(p[0]); all_y.append(p[1])

    for s in all_shapes:
        _collect(s)

    def _perc(arr: list, pct: float) -> float:
        arr_s = sorted(arr)
        idx = max(0, min(len(arr_s) - 1, int(len(arr_s) * pct / 100)))
        return arr_s[idx]

    if all_x:
        x_lo = _perc(all_x, 2);  x_hi = _perc(all_x, 98)
        y_lo = _perc(all_y, 2);  y_hi = _perc(all_y, 98)
        mx = max((x_hi - x_lo) * 0.05, 1.0)
        my = max((y_hi - y_lo) * 0.05, 1.0)
        bbox = {
            "minX": round(x_lo - mx, 4), "minY": round(y_lo - my, 4),
            "maxX": round(x_hi + mx, 4), "maxY": round(y_hi + my, 4),
        }
    else:
        bbox = {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}

    # ── Filtrar outliers e subamostrar entidades não-problemáticas ─────────────
    bx0, bx1 = bbox["minX"], bbox["maxX"]
    by0, by1 = bbox["minY"], bbox["maxY"]

    def _center(g: dict):
        if "x1" in g: return (g["x1"] + g["x2"]) / 2, (g["y1"] + g["y2"]) / 2
        if "cx" in g: return g["cx"], g["cy"]
        if "x"  in g: return g["x"],  g["y"]
        if "points" in g and g["points"]:
            cx = sum(p[0] for p in g["points"]) / len(g["points"])
            cy = sum(p[1] for p in g["points"]) / len(g["points"])
            return cx, cy
        return None

    def _in_bbox(g: dict) -> bool:
        pt = _center(g)
        if pt is None:
            return True
        cx, cy = pt
        return bx0 <= cx <= bx1 and by0 <= cy <= by1

    issue_sh  = [s for s in all_shapes if s["handle"] in issue_handles]
    other_sh  = [s for s in all_shapes if s["handle"] not in issue_handles and _in_bbox(s)]

    # Subsample entidades não-problemáticas se houver muitas
    if len(other_sh) > max_shapes:
        step = max(1, len(other_sh) // max_shapes)
        other_sh = other_sh[::step]

    return {"shapes": issue_sh + other_sh, "bbox": bbox}


class DXFChecker:
    """
    Verifica um arquivo DXF/DWG contra um conjunto de regras configuráveis.

    Exemplo de uso::

        checker = DXFChecker()
        result  = checker.check("planta.dxf")

        print(f"Erros:   {result['errors']}")
        print(f"Avisos:  {result['warnings']}")
        print(f"Aprovado: {result['passed']}")
    """

    def __init__(self, config_path: Optional[str] = None, config_data: Optional[dict] = None) -> None:
        if isinstance(config_data, dict):
            self.config = _validate_config(copy.deepcopy(config_data))
        else:
            path = Path(config_path) if config_path else DEFAULT_CONFIG

            if not path.exists():
                self.config = {}          # config ausente — usa padrões
            else:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.config = yaml.safe_load(f) or {}
                except Exception:
                    self.config = {}      # YAML inválido — usa padrões

            self.config = _validate_config(self.config)
        self.rules  = get_all_rules()

    # ------------------------------------------------------------------

    def check(self, file_path: str, progress_cb=None) -> Dict:
        """
        Executa todas as regras sobre o arquivo informado.

        Returns
        -------
        dict
            Chaves: file, file_path, file_size_mb, entity_count,
                    dxf_version, dxf_version_name, check_time,
                    total_issues, errors, warnings, infos,
                    issues (List[Issue]), passed (bool), geometry, geo_bbox
        """
        t0   = time.time()
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        # ── Metadados do arquivo ───────────────────────────────────────────
        file_size_mb = round(path.stat().st_size / (1024 * 1024), 2)

        # ── SHA-256 (assinatura do arquivo) ────────────────────────────────
        try:
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            sha256 = ""

        # ── Abrir DXF — com fallback de recuperação para arquivos corrompidos
        pre_issues: list[Issue] = []
        try:
            doc = ezdxf.readfile(str(path))
        except Exception as exc_main:
            try:
                import ezdxf.recover as _rec
                doc, auditor = _rec.readfile(str(path))
                for err in (auditor.errors or []):
                    pre_issues.append(Issue(
                        rule="DXF_RECOVERY_WARNING",
                        severity=Severity.WARNING,
                        message="Arquivo com problema estrutural (recuperado automaticamente)",
                        details=str(err),
                    ))
            except Exception as exc_rec:
                raise ValueError(
                    f"Não foi possível abrir o arquivo.\n"
                    f"Erro original: {exc_main}\n"
                    f"Tentativa de recuperação: {exc_rec}"
                ) from exc_rec

        # ── Metadados do documento DXF ─────────────────────────────────────
        _VER = {
            "AC1009": "R12",  "AC1012": "R13",  "AC1014": "R14",
            "AC1015": "R2000","AC1018": "R2004","AC1021": "R2007",
            "AC1024": "R2010","AC1027": "R2013","AC1032": "R2018",
        }
        dxf_version      = getattr(doc, "dxfversion", "?")
        dxf_version_name = _VER.get(dxf_version, dxf_version)
        try:
            entity_count = sum(1 for _ in doc.modelspace())
        except Exception:
            entity_count = 0

        if file_size_mb > 50:
            pre_issues.append(Issue(
                rule="LARGE_FILE",
                severity=Severity.INFO,
                message=f"Arquivo grande ({file_size_mb:.1f} MB) — verificação pode ser mais lenta",
            ))

        # ── Executar regras ────────────────────────────────────────────────
        issues: List[Issue] = list(pre_issues)
        for idx, rule_fn in enumerate(self.rules):
            if progress_cb:
                progress_cb(rule_fn.__name__, idx + 1, len(self.rules))
            try:
                issues.extend(rule_fn(doc, self.config))
            except Exception as exc:  # noqa: BLE001
                issues.append(Issue(
                    rule="RULE_EXECUTION_ERROR",
                    severity=Severity.ERROR,
                    message=f"Erro interno em '{rule_fn.__name__}': {exc}",
                ))

        # ── Extrair geometria para o visualizador ──────────────────────────
        issue_handles = {iss.handle for iss in issues if iss.handle}
        geo_result    = _extract_geometry(doc, issue_handles=issue_handles)

        # ── Aplicar overrides de severidade (config [rules][severity_overrides]) ─
        sev_overrides: dict = self.config.get("rules", {}).get("severity_overrides", {})
        if sev_overrides:
            for iss in issues:
                if iss.rule in sev_overrides:
                    try:
                        iss.severity = Severity(str(sev_overrides[iss.rule]).upper())
                    except ValueError:
                        pass
        return {
            "file":             path.name,
            "file_path":        str(path.resolve()),
            "file_size_mb":     file_size_mb,
            "entity_count":     entity_count,
            "dxf_version":      dxf_version,
            "dxf_version_name": dxf_version_name,
            "check_time":       round(time.time() - t0, 2),
            "total_issues":     len(issues),
            "errors":   sum(1 for i in issues if i.severity == Severity.ERROR),
            "warnings": sum(1 for i in issues if i.severity == Severity.WARNING),
            "infos":    sum(1 for i in issues if i.severity == Severity.INFO),
            "issues":   issues,
            "passed":   all(i.severity != Severity.ERROR for i in issues),
            "geometry": geo_result["shapes"],
            "geo_bbox": geo_result["bbox"],
            "sha256":   sha256,
        }
