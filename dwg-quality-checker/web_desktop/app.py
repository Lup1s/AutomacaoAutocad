from __future__ import annotations

import sys
from pathlib import Path

from .bridge import DesktopBridge


def _resolve_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def _resolve_frontend_index(base_dir: Path) -> Path:
    candidates = [
        base_dir / "web-ui-prototype" / "dist" / "index.html",
        base_dir / "_internal" / "web-ui-prototype" / "dist" / "index.html",
    ]

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(str(meipass)) / "web-ui-prototype" / "dist" / "index.html")

    for path in candidates:
        if path.exists():
            return path

    return candidates[0]


def start_web_desktop() -> None:
    try:
        import webview
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pywebview não instalado. Instale com: pip install pywebview") from exc

    base_dir = _resolve_base_dir()
    index_html = _resolve_frontend_index(base_dir)
    if not index_html.exists():
        expected = [
            str(base_dir / "web-ui-prototype" / "dist" / "index.html"),
            str(base_dir / "_internal" / "web-ui-prototype" / "dist" / "index.html"),
        ]
        raise FileNotFoundError(
            "Frontend não encontrado. Rode: npm --prefix web-ui-prototype run build "
            f"(procurado em: {expected})"
        )

    bridge = DesktopBridge(base_dir=base_dir)

    window = webview.create_window(
        title="DWG Quality Checker",
        url=index_html.as_uri(),
        js_api=bridge,
        width=1500,
        height=900,
        min_size=(1180, 720),
    )
    webview.start(debug=False, gui="edgechromium")
