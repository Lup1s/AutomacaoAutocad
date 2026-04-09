# Release QA — Etapa 4 (Instalador + Smoke + Uninstall)

Data: 2026-04-09
Status: Concluída ✅

## Escopo validado
- Instalação silenciosa em diretório de teste.
- Smoke de boot nos modos: `auto`, `web`, `legacy`.
- Desinstalação silenciosa com limpeza do diretório.
- Rebuild completo de executável e instalador após correções.

## Correções aplicadas
1. Resolução de frontend em build frozen:
   - Busca em caminhos com `_internal` e `_MEIPASS`.
2. Compatibilidade de inicialização do WebView:
   - Ajuste da chamada de `start` sem argumento inválido `window`.

## Evidências técnicas
- Eventos de boot (`ui_boot_events.jsonl`) confirmando resolução de modo e tentativas web sem fallback indevido no smoke final.
- Uninstall com código de saída `0` e remoção do diretório de teste.

## Artefatos finais (pós-fix)
- `dist/DWGQualityChecker/DWGQualityChecker.exe`
  - SHA256: `78061FCE5648A2CDA643BD9AC4968C6D469AA609EC2504228EE573CAF191FF6C`
- `dist_installer/DWGQualityChecker_Setup_v2.7.9.exe`
  - SHA256: `9123C201C2A490DA3BF0183056F3A13115A5C4985BD3EA1BC365DEB52D685F3B`

## Gate para próxima etapa
- Etapa 4 aprovada para avanço.
- Próxima etapa sugerida (Etapa 5): formalização de release (tag/changelog/publicação dos artefatos).
