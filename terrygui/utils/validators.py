"""
Validation utilities for TerryGUI.
"""

import shutil
import subprocess
from typing import Tuple, Optional


def validate_terraform_installed(terraform_binary: str = "terraform") -> Tuple[bool, Optional[str]]:
    """
    Check if Terraform is installed and accessible.
    
    Args:
        terraform_binary: Path or name of terraform binary
        
    Returns:
        Tuple of (is_installed, version_string)
        If not installed, version_string is None
    """
    # Check if binary exists in PATH
    if not shutil.which(terraform_binary):
        return False, None
    
    # Try to get version
    try:
        from . import subprocess_creation_flags
        result = subprocess.run(
            [terraform_binary, "version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess_creation_flags(),
        )
        
        if result.returncode == 0:
            # Parse version from output (first line usually contains version)
            version_line = result.stdout.split('\n')[0]
            return True, version_line
        else:
            return False, None
    
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, None


def validate_project_is_terraform(project_path: str) -> bool:
    """
    Check if a directory appears to be a Terraform project.
    
    A valid Terraform project should have at least one .tf file.
    
    Args:
        project_path: Path to directory
        
    Returns:
        True if appears to be a Terraform project
    """
    import os
    from pathlib import Path
    
    path = Path(project_path)
    
    if not path.exists() or not path.is_dir():
        return False
    
    # Look for .tf files
    tf_files = list(path.glob("*.tf"))
    
    return len(tf_files) > 0
