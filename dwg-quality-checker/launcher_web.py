"""Bootstrap híbrido da UI (web embutida com fallback para legacy)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from web_desktop import start_web_desktop


def _resolve_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _load_boot_config(base_dir: Path) -> dict:
    cfg_file = base_dir / "ui_boot.json"
    if not cfg_file.exists():
        return {}
    try:
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _boot_events_file(base_dir: Path) -> Path:
    return base_dir / "ui_boot_events.jsonl"


def _append_boot_event(base_dir: Path, event: str, details: dict | None = None) -> None:
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        "details": details or {},
    }
    try:
        with _boot_events_file(base_dir).open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _resolve_mode(argv: list[str], cfg: dict) -> tuple[str, bool]:
    """Resolve política de boot.

    mode: auto | web | legacy
    fallback: se pode cair para legacy quando web falhar
    """
    mode = "auto"
    fallback = True

    if "--web" in argv:
        mode = "web"
    elif "--legacy" in argv:
        mode = "legacy"
    else:
        env_mode = str(os.getenv("DWGQC_UI_MODE", "")).strip().lower()
        cfg_mode = str(cfg.get("mode", "")).strip().lower()
        mode = env_mode or cfg_mode or "auto"

    if mode not in {"auto", "web", "legacy"}:
        mode = "auto"

    env_fallback = os.getenv("DWGQC_UI_FALLBACK_LEGACY")
    if env_fallback is not None:
        fallback = str(env_fallback).strip().lower() in {"1", "true", "yes", "on"}
    elif "fallback_to_legacy" in cfg:
        fallback = bool(cfg.get("fallback_to_legacy"))

    return mode, fallback


def _start_legacy(base_dir: Path, reason: str = "") -> None:
    if reason:
        print(f"[DWGQC] fallback para UI legacy: {reason}")
    _append_boot_event(base_dir, "legacy_start", {"reason": reason})
    from launcher import start_legacy_desktop

    start_legacy_desktop(login_only=False)


def _start_web_with_fallback(base_dir: Path, allow_fallback: bool) -> None:
    _append_boot_event(base_dir, "web_attempt", {"allow_fallback": bool(allow_fallback)})
    try:
        _append_boot_event(base_dir, "login_ui_react", {"enabled": True})
        start_web_desktop()
    except Exception as exc:
        _append_boot_event(base_dir, "web_failed", {"error": str(exc)})
        if not allow_fallback:
            raise
        _append_boot_event(base_dir, "fallback_to_legacy", {"reason": str(exc)})
        _start_legacy(base_dir=base_dir, reason=str(exc))


if __name__ == "__main__":
    base_dir = _resolve_base_dir()
    cfg = _load_boot_config(base_dir)
    mode, allow_fallback = _resolve_mode(sys.argv[1:], cfg)
    _append_boot_event(base_dir, "boot_mode_resolved", {"mode": mode, "allow_fallback": allow_fallback})

    if mode == "legacy":
        _start_legacy(base_dir=base_dir, reason="modo legacy forçado")
    elif mode == "web":
        _start_web_with_fallback(base_dir=base_dir, allow_fallback=allow_fallback)
    else:  # auto
        _start_web_with_fallback(base_dir=base_dir, allow_fallback=True)
