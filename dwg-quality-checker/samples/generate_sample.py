"""
Gera um arquivo DXF de exemplo com problemas intencionais para demonstração e testes.

Execute:
    python samples/generate_sample.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o pacote raiz seja encontrado quando rodado diretamente
sys.path.insert(0, str(Path(__file__).parent.parent))

import ezdxf


def create_sample(output_path: str) -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # ── Layers ───────────────────────────────────────────────────────────────
    doc.layers.add("ARQUITETURA", color=1)   # vermelha
    doc.layers.add("ESTRUTURA",   color=2)   # amarela
    doc.layers.add("HIDRAULICA",  color=4)   # ciano
    doc.layers.add("LAYER_VAZIA")            # → INFO: layer sem entidades

    # ── Entidade na layer "0" (má prática) ──────────────────────────────────
    #    Gera: WARNING — ENTITIES_ON_LAYER_0
    msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "0"})
    msp.add_circle((200, 0), 10,  dxfattribs={"layer": "0"})

    # ── Entidades normais ────────────────────────────────────────────────────
    msp.add_line((0, 10), (0, 100),  dxfattribs={"layer": "ARQUITETURA"})
    msp.add_lwpolyline(
        [(0, 0), (50, 0), (50, 50), (0, 50)],
        dxfattribs={"layer": "ESTRUTURA", "closed": True},
    )
    msp.add_circle((25, 25), 10, dxfattribs={"layer": "HIDRAULICA"})

    # ── Textos com altura FORA do padrão ─────────────────────────────────────
    #    Gera: WARNING — TEXT_HEIGHT_OUT_OF_RANGE
    msp.add_text(
        "Texto muito pequeno (h=0.5)",
        dxfattribs={"layer": "ARQUITETURA", "height": 0.5},
    ).set_placement((0, -10))

    msp.add_text(
        "Texto gigante (h=50)",
        dxfattribs={"layer": "ARQUITETURA", "height": 50},
    ).set_placement((0, -20))

    # ── Texto com altura OK ───────────────────────────────────────────────────
    msp.add_text(
        "Texto dentro do padrão (h=2.5)",
        dxfattribs={"layer": "ARQUITETURA", "height": 2.5},
    ).set_placement((0, -30))

    # ── Bloco definido mas NÃO inserido ──────────────────────────────────────
    #    Gera: INFO — UNUSED_BLOCK_DEFINITIONS
    unused = doc.blocks.new("BLOCO_SEM_USO")
    unused.add_circle((0, 0), 5)
    unused.add_text("ID", dxfattribs={"height": 2.0})

    # ── Bloco definido E inserido (normal) ───────────────────────────────────
    caixa = doc.blocks.new("CAIXA_INSPECAO")
    caixa.add_lwpolyline(
        [(-5, -5), (5, -5), (5, 5), (-5, 5)],
        dxfattribs={"closed": True},
    )
    msp.add_blockref("CAIXA_INSPECAO", (60, 60), dxfattribs={"layer": "HIDRAULICA"})

    doc.saveas(output_path)
    print(f"✅  DXF de exemplo gerado: {output_path}")
    print()
    print("Problemas intencionais incluídos:")
    print("  ⚠️  WARNING  — 2 entidades na layer '0'")
    print("  ⚠️  WARNING  — texto com altura 0.5 (abaixo do mínimo 1.5)")
    print("  ⚠️  WARNING  — texto com altura 50  (acima do máximo 10.0)")
    print("  ℹ️  INFO     — 1 layer vazia (LAYER_VAZIA)")
    print("  ℹ️  INFO     — 1 bloco definido sem uso (BLOCO_SEM_USO)")


if __name__ == "__main__":
    out = Path(__file__).parent / "sample_with_issues.dxf"
    create_sample(str(out))
