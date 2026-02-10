"""
Utility functions for TerryGUI.
"""

import subprocess
import sys

from .logger import setup_logging
from .validators import validate_terraform_installed


def subprocess_creation_flags() -> int:
    """Return creationflags to hide console windows on Windows, 0 elsewhere."""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


__all__ = ["setup_logging", "validate_terraform_installed", "subprocess_creation_flags"]
