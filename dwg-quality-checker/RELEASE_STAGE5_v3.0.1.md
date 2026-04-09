# Release Stage 5 — v3.0.1

Data: 2026-04-09
Status: Concluída ✅

## Objetivo da etapa
Formalizar a release após QA da Etapa 4, consolidando versão, changelog, artefatos finais e checklist de publicação.

## Entregas da etapa
- Versão do produto atualizada para `3.0.1`.
- Changelog da versão criado em `CHANGELOG.md`.
- Metadados de build e instalador sincronizados para `3.0.1`.
- Novo executável e novo instalador gerados.

## Checklist de publicação
- [x] Atualizar versão (`checker/version.py`).
- [x] Sincronizar metadados (`build/sync_version_metadata.py --write`).
- [x] Build frontend React (`npm run build`).
- [x] Build executável (`build/build.bat`).
- [x] Build instalador Inno Setup (`build/installer.iss`).
- [x] Gerar hashes SHA256 dos artefatos finais.

## Artefatos finais
- Executável: `dist/DWGQualityChecker/DWGQualityChecker.exe`
- Instalador: `dist_installer/DWGQualityChecker_Setup_v3.0.1.exe`

## Próximo passo operacional
Publicar release no GitHub com tag `v3.0.1` e anexar os artefatos acima.
