# 🏗️ DWG Quality Checker

> Automated quality checker for DXF/DWG CAD files — validates layer standards,
> text heights, block definitions and more. **No AutoCAD license required.**

[![CI](https://github.com/yourusername/dwg-quality-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/dwg-quality-checker/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

| Check | Severity | Description |
|-------|----------|-------------|
| Required layers | ❌ ERROR | Ensures mandatory layers are present |
| Entities on Layer 0 | ⚠️ WARNING | Detects bad practice of drawing on layer 0 |
| Frozen layers with entities | ⚠️ WARNING | Finds entities hidden by frozen layers |
| Off layers with entities | ℹ️ INFO | Entities on turned-off layers |
| Empty layers | ℹ️ INFO | Layer definitions without any entities |
| Layer naming convention | ⚠️ WARNING | Validates names against a regex pattern |
| Text height range | ⚠️ WARNING | Flags texts outside defined min/max height |
| Unused block definitions | ℹ️ INFO | Block definitions never inserted in model space |

---

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/dwg-quality-checker.git
cd dwg-quality-checker

# 2. Install dependencies (no AutoCAD needed!)
pip install -r requirements.txt

# 3. Generate a sample DXF with intentional issues
python samples/generate_sample.py

# 4. Run the checker
python main.py samples/sample_with_issues.dxf
```

---

## 📖 Usage

```
python main.py <file.dxf> [options]

positional arguments:
  file                        Path to DXF/DWG file

options:
  -o, --output {console,html,csv,all}   Output format (default: console)
  -f, --output-file NAME                Base name for the output file
  -c, --config FILE                     Custom YAML configuration file
      --strict                          Exit code 1 if any ERRORs found (CI/CD)
```

### Examples

```bash
# Console output (default)
python main.py planta.dxf

# Generate HTML report
python main.py planta.dxf --output html

# Generate HTML + CSV
python main.py planta.dxf --output all --output-file reports/planta_report

# Use custom config and fail the pipeline on errors
python main.py planta.dxf --config standards/company_rules.yaml --strict
```

---

## ⚙️ Configuration

Edit `config.yaml` to match your office standards:

```yaml
layers:
  required:
    - "TEXTO"
    - "COTA"
    - "HACHURA"
  naming_convention: "^[A-Z]{2,4}-[A-Z0-9_-]+$"   # e.g. ARQ-PAREDE

text:
  min_height: 1.5
  max_height: 10.0

drawing:
  check_entities_on_layer_0: true
  check_unused_blocks: true
  check_empty_layers: true
  check_frozen_layers: true
  check_off_layers: true
```

---

## 📂 Project Structure

```
dwg-quality-checker/
├── checker/
│   ├── __init__.py
│   ├── core.py          # DXFChecker class — orchestrates all rules
│   ├── rules.py         # All checking rules (easily extensible)
│   └── report.py        # Report generators: console, HTML, CSV
├── templates/
│   └── report.html      # Jinja2 HTML report template
├── samples/
│   └── generate_sample.py   # Creates a sample DXF with intentional issues
├── .github/
│   └── workflows/
│       └── ci.yml       # GitHub Actions — runs checker on every push
├── main.py              # CLI entry point
├── config.yaml          # Rules configuration
└── requirements.txt
```

---

## 🛠️ Tech Stack

| Library | Purpose |
|---------|---------|
| [ezdxf](https://ezdxf.readthedocs.io/) | Read DXF/DWG files — no AutoCAD required |
| [Rich](https://rich.readthedocs.io/) | Beautiful terminal output with tables |
| [Jinja2](https://jinja.palletsprojects.com/) | HTML report templating |
| [PyYAML](https://pyyaml.org/) | YAML configuration parsing |

---

## 🤝 Adding Custom Rules

Every rule is a plain Python function — just add it to `checker/rules.py` and register it in `get_all_rules()`:

```python
def check_my_rule(doc: ezdxf.document.Drawing, config: dict) -> List[Issue]:
    issues = []
    # ... your logic here ...
    return issues
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
