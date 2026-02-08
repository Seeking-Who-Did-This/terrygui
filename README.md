# TerryGUI

A Qt-based GUI for managing Terraform projects.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

## Features

### Current (v1.0.0)
- Secure project loading and validation
- Terraform configuration parsing (HCL)
- Variable detection with type and sensitivity analysis
- Project state management (.tfgui files)
- Automatic .gitignore management
- Cross-platform support (Linux, Windows)

### Planned
- Terraform command execution (init, validate, plan, apply, destroy)
- Workspace management
- State viewing and inspection
- .tfvars import/export

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/yourusername/terrygui.git
cd terrygui

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Pre-built Binaries

Download pre-built binaries from the [Releases](https://github.com/yourusername/terrygui/releases) page:
- `terrygui-linux-x86_64` - Linux standalone executable
- `terrygui-windows-x86_64.exe` - Windows standalone executable

## Requirements

- Python 3.8 or higher
- Terraform installed and in PATH
- PySide6 (Qt6)
- python-hcl2

## Usage

### Basic Workflow

1. **Launch TerryGUI**
   ```bash
   python main.py
   ```

2. **Open a Terraform Project**
   - Click "Browse" or use File → Open Project
   - Select your Terraform project directory

3. **Review Variables**
   - Variables from `.tf` files are automatically detected
   - Required variables are marked
   - Sensitive variables are protected

### Project State Management

TerryGUI creates a `.tfgui` file in your project directory to store:
- Last active workspace
- Non-sensitive variable values
- UI preferences

This file is automatically added to `.gitignore`.

## Security Features

### Input Validation
- Path traversal prevention
- Command injection protection
- Terraform variable name/value validation
- Workspace name validation

### Sensitive Data Handling
- Sensitive variables never persisted to disk
- Automatic output redaction
- Secure memory cleanup
- Password-style input masking

### Process Isolation
- No shell interpretation (`shell=False`)
- Proper argument escaping
- Process timeout protection
- Resource limit enforcement

## Configuration

### Application Settings

Settings are stored in:
- **Linux/macOS**: `~/.config/terrygui/settings.json`
- **Windows**: `%APPDATA%\terrygui\settings.json`

### Configurable Options

```json
{
  "editor_command": "code",
  "terraform_binary": "terraform",
  "default_debug_output": false,
  "confirmations": {
    "apply": true,
    "destroy": true
  }
}
```

### Editor Configuration

By default, TerryGUI uses VSCode (`code`) to open projects. Configure a different editor by modifying the settings file:

```json
{
  "editor_command": "/usr/bin/vim"
}
```

## Development

### Project Structure

```
terrygui/
├── main.py                     # Application entry point
├── terrygui/
│   ├── ui/                     # User interface components
│   ├── core/                   # Business logic
│   ├── security/               # Security utilities
│   ├── config/                 # Configuration management
│   └── utils/                  # Utility functions
└── tests/                      # Test suite
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-qt

# Run all tests
pytest

# Run with coverage
pytest --cov=terrygui --cov-report=html
```

### Building from Source

#### Linux

```bash
pip install pyinstaller
pyinstaller --name=terrygui \
            --windowed \
            --onefile \
            --add-data="terrygui:terrygui" \
            main.py
```

#### Windows

```powershell
pip install pyinstaller
pyinstaller --name=terrygui `
            --windowed `
            --onefile `
            --add-data="terrygui;terrygui" `
            main.py
```

The built executable will be in the `dist/` directory.

## Troubleshooting

### Terraform Not Found

**Error**: "Terraform not found. Install or configure path in Settings."

**Solution**: 
- Install Terraform from https://www.terraform.io/downloads
- Ensure `terraform` is in your PATH
- Or configure custom path in settings:
  ```json
  {
    "terraform_binary": "/custom/path/to/terraform"
  }
  ```

### Project Won't Load

**Error**: "Directory does not appear to be a Terraform project"

**Solution**:
- Ensure directory contains at least one `.tf` file
- Check file permissions
- Verify HCL syntax is valid

### Editor Won't Open

**Error**: "Failed to open project in editor"

**Solution**:
- Ensure configured editor is installed
- Check editor command in settings
- Try full path: `"editor_command": "/usr/bin/code"`

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [PySide6](https://wiki.qt.io/Qt_for_Python)
- HCL parsing by [python-hcl2](https://github.com/amplify-education/python-hcl2)
