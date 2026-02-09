"""
Core Terraform management functionality for TerryGUI.

This module provides the business logic for interacting with Terraform:
- Parsing Terraform configuration files
- Managing project state
- Executing Terraform commands
"""

from .terraform_parser import TerraformParser, TerraformVariable
from .project_manager import ProjectManager
from .terraform_runner import TerraformRunner, CommandResult

__all__ = [
    "TerraformParser",
    "TerraformVariable",
    "ProjectManager",
    "TerraformRunner",
    "CommandResult",
]
