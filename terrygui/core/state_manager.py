"""
Terraform state inspection.

Provides read-only access to Terraform state: listing resources,
showing resource details, and viewing outputs.
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import List, Tuple

from ..security.sanitizer import InputSanitizer, SecurityError
from ..utils import subprocess_creation_flags

logger = logging.getLogger(__name__)

# Allowed pattern for resource addresses: type.name, module.x.type.name, etc.
_RESOURCE_ADDRESS_RE = re.compile(r'^[\w.\[\]":-]+$')


@dataclass
class StateResource:
    """A single resource in Terraform state."""
    address: str       # e.g. "aws_instance.web"
    type: str          # e.g. "aws_instance"
    name: str          # e.g. "web"
    provider: str      # extracted from details if available


@dataclass
class StateSummary:
    """Summary of Terraform state."""
    resources: List[StateResource]
    total_count: int


class StateManager:
    """
    Read-only Terraform state inspection.

    All commands run synchronously (they're fast) and use the same
    security patterns as WorkspaceManager: shell=False, validated args,
    timeouts.
    """

    def __init__(self, project_path: str, terraform_binary: str = "terraform"):
        self.project_path = project_path
        self.terraform_binary = terraform_binary

    def _run(self, args: List[str], timeout: int = 15) -> Tuple[int, str, str]:
        """
        Run a terraform subcommand.

        Returns:
            (exit_code, stdout, stderr)
        """
        cmd = [
            self.terraform_binary,
            f"-chdir={self.project_path}",
        ] + args

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

    @staticmethod
    def _validate_resource_address(address: str) -> None:
        """Validate a resource address to prevent injection."""
        if not address or not _RESOURCE_ADDRESS_RE.match(address):
            raise SecurityError(f"Invalid resource address: {address}")

    @staticmethod
    def _parse_address(address: str) -> Tuple[str, str]:
        """
        Split a resource address into (type, name).

        For simple addresses like "aws_instance.web", returns ("aws_instance", "web").
        For module addresses like "module.foo.aws_instance.web", returns ("aws_instance", "web").
        """
        parts = address.split(".")
        if len(parts) >= 2:
            return parts[-2], parts[-1]
        return address, ""

    def list_resources(self) -> List[StateResource]:
        """
        List all resources in the current Terraform state.

        Runs `terraform state list` and parses each line as a resource address.
        """
        code, stdout, stderr = self._run(["state", "list"])
        if code != 0:
            logger.error(f"Failed to list state resources: {stderr}")
            return []

        resources = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            res_type, res_name = self._parse_address(line)
            resources.append(StateResource(
                address=line,
                type=res_type,
                name=res_name,
                provider="",
            ))

        return resources

    def get_resource_details(self, address: str) -> str:
        """
        Get detailed attributes for a single resource.

        Runs `terraform state show <address>` and returns the
        redacted output.
        """
        self._validate_resource_address(address)
        code, stdout, stderr = self._run(["state", "show", "-no-color", address])
        if code != 0:
            logger.error(f"Failed to show resource {address}: {stderr}")
            return f"Error: {stderr}"

        return stdout

    def get_outputs(self) -> str:
        """
        Get all Terraform outputs.

        Runs `terraform output -no-color` and returns the redacted output.
        """
        code, stdout, stderr = self._run(["output", "-no-color"])
        if code != 0:
            logger.error(f"Failed to get outputs: {stderr}")
            return f"Error: {stderr}"

        return stdout
