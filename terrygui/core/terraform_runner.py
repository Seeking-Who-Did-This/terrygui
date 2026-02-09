"""
Terraform command execution with real-time output streaming.

This module provides secure execution of Terraform commands
(init, validate, plan, apply, destroy) with output redaction,
streaming callbacks, and process management.
"""

import subprocess
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..security.sanitizer import InputSanitizer, SecurityError
from ..security.secure_memory import OutputRedactor


@dataclass
class CommandResult:
    """Result of a Terraform command execution."""
    exit_code: int
    stdout: str
    stderr: str
    success: bool
    command: str  # operation name (e.g. "init", "plan")


class TerraformRunner:
    """
    Executes Terraform commands securely with real-time output streaming.

    Security features:
    - All paths validated via InputSanitizer
    - shell=False always (no shell interpretation)
    - -input=false prevents stdin prompts
    - Output redaction for sensitive values
    - Process timeout (default 300s)
    - All command args validated via is_safe_command_arg()
    """

    def __init__(
        self,
        project_path: str,
        terraform_binary: str = "terraform",
        debug: bool = False,
    ):
        self.project_path = InputSanitizer.sanitize_path(project_path)
        self.terraform_binary = terraform_binary
        self.debug = debug
        self._redactor = OutputRedactor()
        self._process: Optional[subprocess.Popen] = None
        self._timeout = 300

    def set_redactor(self, redactor: OutputRedactor):
        """Configure output redaction for sensitive values."""
        self._redactor = redactor

    def cancel(self):
        """Terminate any running subprocess."""
        if self._process is not None:
            try:
                self._process.terminate()
            except OSError:
                pass

    def init(
        self,
        backend_config: Optional[Dict[str, str]] = None,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """Run terraform init."""
        cmd = self._build_base_command("init")
        cmd.extend(["-input=false", "-no-color"])

        if backend_config:
            for key, value in backend_config.items():
                InputSanitizer.sanitize_variable_name(key)
                sanitized = InputSanitizer.sanitize_variable_value(value)
                arg = f"-backend-config={key}={sanitized}"
                if not InputSanitizer.is_safe_command_arg(arg):
                    raise SecurityError(f"Unsafe backend-config argument: {key}")
                cmd.append(arg)

        return self._execute(cmd, "init", output_callback)

    def validate(
        self,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """Run terraform validate."""
        cmd = self._build_base_command("validate")
        cmd.append("-no-color")
        return self._execute(cmd, "validate", output_callback)

    def plan(
        self,
        variables: Optional[Dict[str, Any]] = None,
        var_types: Optional[Dict[str, str]] = None,
        out_file: Optional[str] = None,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """Run terraform plan."""
        cmd = self._build_base_command("plan")
        cmd.extend(["-input=false", "-no-color"])

        if variables:
            self._add_variables(cmd, variables, var_types or {})

        if out_file:
            if not InputSanitizer.is_safe_command_arg(out_file):
                raise SecurityError(f"Unsafe out file path: {out_file}")
            cmd.append(f"-out={out_file}")

        return self._execute(cmd, "plan", output_callback)

    def apply(
        self,
        variables: Optional[Dict[str, Any]] = None,
        var_types: Optional[Dict[str, str]] = None,
        auto_approve: bool = False,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """Run terraform apply."""
        cmd = self._build_base_command("apply")
        cmd.extend(["-input=false", "-no-color"])

        if auto_approve:
            cmd.append("-auto-approve")

        if variables:
            self._add_variables(cmd, variables, var_types or {})

        return self._execute(cmd, "apply", output_callback)

    def destroy(
        self,
        variables: Optional[Dict[str, Any]] = None,
        var_types: Optional[Dict[str, str]] = None,
        auto_approve: bool = False,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """Run terraform destroy."""
        cmd = self._build_base_command("destroy")
        cmd.extend(["-input=false", "-no-color"])

        if auto_approve:
            cmd.append("-auto-approve")

        if variables:
            self._add_variables(cmd, variables, var_types or {})

        return self._execute(cmd, "destroy", output_callback)

    def _build_base_command(self, operation: str) -> List[str]:
        """Construct the base command list [binary, -chdir=path, operation]."""
        chdir_arg = f"-chdir={self.project_path}"
        if not InputSanitizer.is_safe_command_arg(chdir_arg):
            raise SecurityError("Unsafe project path for command argument")
        return [self.terraform_binary, chdir_arg, operation]

    def _add_variables(
        self,
        cmd: List[str],
        variables: Dict[str, Any],
        var_types: Dict[str, str],
    ):
        """Validate and append -var arguments to the command list."""
        for name, value in variables.items():
            InputSanitizer.sanitize_variable_name(name)
            var_type = var_types.get(name, "string")
            sanitized_value = InputSanitizer.sanitize_variable_value(value, var_type)
            arg = f"{name}={sanitized_value}"
            if not InputSanitizer.is_safe_command_arg(arg):
                raise SecurityError(f"Unsafe variable argument: {name}")
            cmd.extend(["-var", arg])

    def _execute(
        self,
        cmd: List[str],
        operation: str,
        output_callback: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """
        Execute a command with real-time output streaming.

        Uses shell=False, streams stdout/stderr line-by-line, applies
        output redaction, and enforces a timeout.
        """
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )

            def _read_stderr():
                assert self._process is not None
                assert self._process.stderr is not None
                for line in self._process.stderr:
                    redacted = self._redactor.redact(line.rstrip("\n"))
                    stderr_lines.append(redacted)
                    if output_callback:
                        output_callback(redacted)

            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            assert self._process.stdout is not None
            for line in self._process.stdout:
                redacted = self._redactor.redact(line.rstrip("\n"))
                stdout_lines.append(redacted)
                if output_callback:
                    output_callback(redacted)

            stderr_thread.join(timeout=self._timeout)
            self._process.wait(timeout=self._timeout)
            exit_code = self._process.returncode

        except subprocess.TimeoutExpired:
            if self._process is not None:
                self._process.terminate()
            return CommandResult(
                exit_code=-1,
                stdout="\n".join(stdout_lines),
                stderr="Command timed out",
                success=False,
                command=operation,
            )
        finally:
            self._process = None

        return CommandResult(
            exit_code=exit_code,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
            success=exit_code == 0,
            command=operation,
        )
