# 🏗️ DWG Quality Checker

Verificador de qualidade para arquivos **DXF/DWG** com foco em padronização técnica, diagnóstico de erros e relatórios acionáveis.

## Principais recursos

- Verificação automática por regras (layers, textos, blocos, XREF, duplicatas, viewport, plot styles etc.)
- Interface desktop (GUI) com:
  - verificação individual
  - lote
  - histórico
  - watch folder
  - comparação entre revisões
- Relatórios em **HTML, CSV, PDF, XLSX**
- Dashboard HTML de lote
- Anotação DXF com layer `_QC_ISSUES`
- CLI para automação/CI

---

## Requisitos

- Python 3.10+
- Windows (GUI otimizada para Windows)

Instalação de dependências:

```bash
pip install -r requirements.txt
```

---

## Como executar

### GUI (recomendado)

```bash
python launcher.py
```

### GUI híbrida (React embutido + fallback)

```bash
python launcher_web.py
```

Política de boot da UI híbrida:

- padrão: `auto` (tenta WebView primeiro e cai para UI legacy se falhar)
- forçar web: `python launcher_web.py --web`
- forçar legacy: `python launcher_web.py --legacy`
- via ambiente: `DWGQC_UI_MODE=auto|web|legacy`
- fallback controlável por `DWGQC_UI_FALLBACK_LEGACY=1|0`

Também é possível criar `ui_boot.json` na pasta do app:

```json
{
  "mode": "auto",
  "fallback_to_legacy": true
}
```

Telemetria local de boot/fallback é registrada em `ui_boot_events.jsonl`.

### CLI oficial

Opção 1:

```bash
python launcher.py --cli arquivo.dxf
```

Opção 2:

```bash
python -m checker.cli arquivo.dxf
```

> `main.py` foi mantido por compatibilidade e delega para `checker.cli`.

---

## CLI — exemplos

```bash
# Verificação simples (gera HTML por padrão)
python launcher.py --cli samples/sample_with_issues.dxf

# Gerar todos os formatos de relatório
python launcher.py --cli samples/sample_with_issues.dxf --output all

# Pasta de saída customizada
python launcher.py --cli samples/sample_with_issues.dxf --out-dir ./reports

# Gerar DXF anotado
python launcher.py --cli samples/sample_with_issues.dxf --annotate

# Saída JSON para automação
python launcher.py --cli samples/sample_with_issues.dxf --json

# Aplicar perfil de norma/disciplina (ex.: elétrica)
python launcher.py --cli samples/sample_with_issues.dxf --profile NBR_5410

# Aplicar múltiplas NBRs no mesmo arquivo (repita --profile ou use vírgula)
python launcher.py --cli samples/sample_with_issues.dxf --profile NBR_5410 --profile NBR_9050
python launcher.py --cli samples/sample_with_issues.dxf --profile NBR_5410,NBR_9050

# Arquivo de perfis customizado
python launcher.py --cli samples/sample_with_issues.dxf --profile NBR_5410 --profiles-file ./config_profiles.json

# Timeout por arquivo (robustez em lote)
python launcher.py --cli samples/sample_with_issues.dxf --timeout-seconds 30

# Log estruturado JSONL por execução
python launcher.py --cli samples/sample_with_issues.dxf --json-log ./logs/run.jsonl

# Resumo agregado da execução em JSON
python launcher.py --cli samples/sample_with_issues.dxf --summary-json ./logs/summary.json

# Desativar cache por conteúdo (SHA-256)
python launcher.py --cli samples/sample_with_issues.dxf --no-cache
```

Códigos de saída:
- `0`: sem falhas críticas
- `1`: houve arquivo com erro/falha

---

## Testes

Executar suíte unitária:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## Build e release (Windows)

1) Sincronizar metadados de versão:

```bash
python build/sync_version_metadata.py --check
```

2) Gerar executável (`dist/DWGQualityChecker`):

```bash
build\build.bat
```

Observações do build híbrido:
- o script gera automaticamente `web-ui-prototype/dist` antes do PyInstaller;
- o executável final (`DWGQualityChecker.exe`) usa bootstrap híbrido (`launcher_web.py`) com fallback para UI legacy;
- `ui_boot.json` padrão é copiado para o `dist` a partir de `ui_boot.example.json`.

3) Gerar instalador (`dist_installer`):
- Abrir [build/installer.iss](build/installer.iss) no Inno Setup.
- Compilar (F9).

### Opções de limpeza no instalador

- **Instalação limpa**: no assistente de instalação, marque a tarefa **Instalação limpa** para remover vestígios de versões antigas antes da cópia da nova versão.
- **Desinstalação limpa**: ao desinstalar, o assistente pergunta se deseja limpeza completa de vestígios e dados residuais do aplicativo.

---

## Estrutura do projeto

```text
dwg-quality-checker/
├── checker/
│   ├── core.py        # Orquestra leitura + execução de regras
│   ├── rules.py       # Regras de validação
│   ├── report.py      # Geração de relatórios (HTML/CSV/PDF/XLSX/dashboard)
│   ├── annotate.py    # Anotação DXF (_QC_ISSUES)
│   ├── cli.py         # CLI oficial
│   └── version.py     # Versão e metadados (fonte única)
├── templates/
│   └── report.html    # Template do relatório interativo
├── launcher.py        # Aplicação GUI
├── main.py            # Entrypoint de compatibilidade (delegação para CLI)
├── config.yaml        # Configurações das regras
├── build/             # Scripts e metadados de empacotamento
├── tests/             # Suíte de testes unitários
└── requirements.txt
```

---

## Configuração

Edite `config.yaml` para adequar padrões da equipe (layers obrigatórias, regex de nomenclatura, limites de texto, regras habilitadas e overrides de severidade).

Para variações por disciplina/norma, utilize perfis em `config_profiles.json` e selecione o perfil na GUI ou via CLI (`--profile`).

Exemplo (trecho):

```yaml
layers:
  required: ["TEXTO", "COTA", "EIXO"]
  naming_convention: "^[A-Z]{2,8}(-[A-Z0-9_-]+)?$"

text:
  min_height: 0.5
  max_height: 20.0

drawing:
  check_entities_on_layer_0: true
  check_duplicates: true
  check_xrefs: true

rules:
  severity_overrides:
    DUPLICATE_ENTITIES: ERROR
    EXTERNAL_FONT: WARNING
```

---

## Versão

Versão atual: **3.0.1**

---

## Licença

Uso interno / distribuição conforme estratégia do projeto.
