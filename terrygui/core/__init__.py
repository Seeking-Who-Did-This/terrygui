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
from .workspace_manager import WorkspaceManager, WorkspaceInfo
from .state_manager import StateManager, StateResource, StateSummary
from .tfvars_handler import TfvarsHandler

__all__ = [
    "TerraformParser",
    "TerraformVariable",
    "ProjectManager",
    "TerraformRunner",
    "CommandResult",
    "WorkspaceManager",
    "WorkspaceInfo",
    "StateManager",
    "StateResource",
    "StateSummary",
    "TfvarsHandler",
]
