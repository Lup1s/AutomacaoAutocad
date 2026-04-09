# DWG Quality Checker — Web UI Prototype

Protótipo da nova interface principal usando **React + TypeScript**.

## Local

1. Instale dependências:
   - `npm install`
2. Rode em desenvolvimento:
   - `npm run dev`
3. Build de produção:
   - `npm run build`

## Escopo deste protótipo

- Recria visualmente a tela principal atual (header, controles, status e tabela).
- Inclui abas/janelas principais: Principal, Lote, Histórico, Watch, Comparar, Config, Sobre e Diagnóstico.
- Serve como base para migração visual mantendo backend Python.

## Modo desktop (instalável, não web app)

O projeto ganhou um runtime híbrido em Python:

- Entrada: [launcher_web.py](../launcher_web.py)
- Ponte Python↔UI: [web_desktop/bridge.py](../web_desktop/bridge.py)

Fluxo:

1. Build do frontend (`npm run build`)
2. Executar `python launcher_web.py`
3. A interface React abre embutida em janela desktop (WebView), sem depender de navegador público.

### Política de fallback (Etapa 2)

`launcher_web.py` agora suporta fallback automático:

- `auto` (padrão): tenta UI web embutida e cai para UI legacy se falhar.
- `--web`: força tentativa web (com fallback configurável).
- `--legacy`: abre direto a UI legacy.

Variáveis/arquivo de controle:

- `DWGQC_UI_MODE=auto|web|legacy`
- `DWGQC_UI_FALLBACK_LEGACY=1|0`
- `ui_boot.json` na raiz do app, por exemplo:

```json
{
   "mode": "auto",
   "fallback_to_legacy": true
}
```

Eventos de boot/fallback são gravados em `ui_boot_events.jsonl` na raiz do app.

## Pasta

- `web-ui-prototype/`
