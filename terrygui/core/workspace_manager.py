"""
Terraform workspace management.

Provides workspace listing, switching, creation, and deletion
by wrapping terraform workspace CLI commands.
"""

import logging
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..security.sanitizer import InputSanitizer, SecurityError
from ..utils import subprocess_creation_flags

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceInfo:
    """Information about a single Terraform workspace."""
    name: str
    is_current: bool


class WorkspaceManager:
    """
    Manage Terraform workspaces for a project.

    All commands run synchronously (they're fast) and use the same
    security patterns as TerraformRunner: shell=False, validated args,
    timeouts.
    """

    def __init__(self, project_path: str, terraform_binary: str = "terraform"):
        self.project_path = project_path
        self.terraform_binary = terraform_binary

    def _run(self, args: List[str], timeout: int = 15) -> Tuple[int, str, str]:
        """
        Run a terraform workspace subcommand.

        Returns:
            (exit_code, stdout, stderr)
        """
        cmd = [
            self.terraform_binary,
            f"-chdir={self.project_path}",
        ] + args

        # Validate all args
        for arg in cmd:
            if not InputSanitizer.is_safe_command_arg(arg):
                raise SecurityError(f"Unsafe command argument: {arg}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                creationflags=subprocess_creation_flags(),
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except OSError as e:
            return -1, "", str(e)

    def get_current_workspace(self) -> str:
        """Return the name of the current workspace."""
        code, stdout, stderr = self._run(["workspace", "show"])
        if code == 0:
            return stdout.strip()
        logger.error(f"Failed to get current workspace: {stderr}")
        return "default"

    def list_workspaces(self) -> List[WorkspaceInfo]:
        """
        List all workspaces for this project.

        Returns:
            List of WorkspaceInfo, with is_current set on the active one.
        """
        code, stdout, stderr = self._run(["workspace", "list"])
        if code != 0:
            logger.error(f"Failed to list workspaces: {stderr}")
            return [WorkspaceInfo(name="default", is_current=True)]

        workspaces = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("* "):
                workspaces.append(WorkspaceInfo(name=line[2:].strip(), is_current=True))
            else:
                workspaces.append(WorkspaceInfo(name=line, is_current=False))

        return workspaces if workspaces else [WorkspaceInfo(name="default", is_current=True)]

    def switch_workspace(self, name: str) -> bool:
        """
        Switch to an existing workspace.

        Args:
            name: Workspace name (validated)

        Returns:
            True if switch succeeded.
        """
        InputSanitizer.sanitize_workspace_name(name)
        code, stdout, stderr = self._run(["workspace", "select", name])
        if code == 0:
            logger.info(f"Switched to workspace: {name}")
            return True
        logger.error(f"Failed to switch workspace: {stderr}")
        return False

    def create_workspace(self, name: str) -> bool:
        """
        Create a new workspace and switch to it.

        Args:
            name: Workspace name (validated)

        Returns:
            True if creation succeeded.
        """
        InputSanitizer.sanitize_workspace_name(name)
        code, stdout, stderr = self._run(["workspace", "new", name])
        if code == 0:
            logger.info(f"Created workspace: {name}")
            return True
        logger.error(f"Failed to create workspace: {stderr}")
        return False

    def delete_workspace(self, name: str, force: bool = False) -> bool:
        """
        Delete a workspace.

        Cannot delete the currently selected workspace.

        Args:
            name: Workspace name (validated)
            force: Force deletion even if workspace has resources

        Returns:
            True if deletion succeeded.
        """
        InputSanitizer.sanitize_workspace_name(name)
        cmd = ["workspace", "delete"]
        if force:
            cmd.append("-force")
        cmd.append(name)
        code, stdout, stderr = self._run(cmd)
        if code == 0:
            logger.info(f"Deleted workspace: {name}")
            return True
        logger.error(f"Failed to delete workspace: {stderr}")
        return False
