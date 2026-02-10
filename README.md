# TerryGUI

A Qt-based GUI for managing Terraform projects.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

## Features

- **Terraform lifecycle management** — run init, validate, plan, apply, and destroy from the GUI with real-time streamed output
- **Variable editing** — type-aware input fields (string, number, bool, list/map/object) with validation, sensitive variable masking, and persistence of non-sensitive values
- **Workspace management** — create, switch, and delete Terraform workspaces via the Workspace menu
- **State inspection** — view resources and outputs from Terraform state
- **.tfvars import/export** — load variable values from `.tfvars` files or export current values
- **Recent projects** — quick access to previously opened projects
- **Preferences** — configurable editor command, Terraform binary path, and confirmation dialog toggles
- **Keyboard shortcuts** — Init (Ctrl+I), Plan (Ctrl+P), Apply (Ctrl+Shift+A), Refresh (F5)
- **Cross-platform** — runs on Linux and Windows, with pre-built binaries available
- **Security-first design** — all subprocess calls use `shell=False`, inputs are validated against injection, sensitive values are redacted from output and never persisted

## Installation

### From Source

```bash
git clone https://github.com/Seeking-Who-Did-This/terrygui.git
cd terrygui
pip install -r requirements.txt
python main.py
```

### Pre-built Binaries

Download pre-built binaries from the [Releases](https://github.com/Seeking-Who-Did-This/terrygui/releases) page:
- `terrygui-linux-x86_64` — Linux standalone executable
- `terrygui-windows-x86_64.exe` — Windows standalone executable

## Requirements

- Python 3.8+
- Terraform installed and in PATH (or configured via preferences)
- PySide6 (Qt6)
- python-hcl2

## Usage

1. **Open a project** — File > Browse project (Ctrl+O), then select a directory containing `.tf` files
2. **Review variables** — variables are parsed automatically; required fields are marked, sensitive fields are masked
3. **Run operations** — click Init, then Plan/Apply/Destroy; output streams in real time
4. **Manage workspaces** — use the Workspace menu to create, delete, or refresh workspaces
5. **Import/export values** — File > Import .tfvars / Export .tfvars
6. **Configure** — File > Edit Preferences to set editor command, Terraform binary, and confirmation toggles

### Project State

TerryGUI stores per-project state in a `.tfgui` file (auto-added to `.gitignore`):
- Last active workspace
- Non-sensitive variable values
- UI preferences

### Application Settings

Stored at:
- **Linux/macOS**: `~/.config/terrygui/settings.json`
- **Windows**: `%APPDATA%\terrygui\settings.json`

Key settings:
```json
{
  "editor_command": "code",
  "terraform_binary": "terraform",
  "confirmations": {
    "apply": true,
    "destroy": true,
    "workspace_delete": true
  }
}
```

## Security

- **Input validation** — path traversal prevention, command injection protection, variable name/value sanitization, workspace name validation
- **Sensitive data** — never persisted to disk, redacted from command output, password-masked in the UI, cleared from memory on exit
- **Process isolation** — `shell=False` on all subprocess calls, argument validation, timeouts, hidden console windows on Windows

## Development

### Project Structure

```
terrygui/
├── main.py                     # Entry point
├── terrygui/
│   ├── config/                 # Settings and defaults
│   ├── core/                   # Parser, runner, workspace/state managers, tfvars handler
│   ├── security/               # Input sanitizer, secure memory, output redactor
│   ├── ui/
│   │   ├── main_window.py      # Main application window
│   │   ├── widgets/            # Variable inputs, output viewer, state viewer
│   │   └── dialogs/            # Confirm, workspace, settings dialogs
│   └── utils/                  # Validators, logging, platform helpers
└── tests/                      # 139 tests across 7 files
```

### Running Tests

```bash
pip install pytest pytest-qt pytest-cov
pytest tests/ -v
```

### Building

```bash
pip install pyinstaller
```

**Linux:**
```bash
pyinstaller --name=terrygui --windowed --onefile \
    --collect-data=hcl2 --collect-data=lark \
    --add-data="terrygui:terrygui" main.py
```

**Windows (PowerShell):**
```powershell
pyinstaller --name=terrygui --windowed --onefile `
    --collect-data=hcl2 --collect-data=lark `
    --add-data="terrygui;terrygui" main.py
```

The `--collect-data` flags are required to bundle the HCL grammar files used by `python-hcl2`.

## Troubleshooting

**Terraform not found** — install Terraform and ensure it's in PATH, or set the path in File > Edit Preferences.

**Project won't load** — the directory must contain at least one `.tf` file with valid HCL syntax.

**Editor won't open** — set the full path to your editor in File > Edit Preferences (e.g. `C:\Program Files\...`).

**Variables not parsed in compiled binary** — ensure the build includes `--collect-data=hcl2 --collect-data=lark`.

## License

MIT License. See [LICENSE](LICENSE) for details.
