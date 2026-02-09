"""
Handler for .tfvars file import/export.

Provides parsing and writing of Terraform variable definition files.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TfvarsHandler:
    """Parse and write Terraform .tfvars files."""

    @staticmethod
    def parse_tfvars(file_path: str) -> dict[str, Any]:
        """
        Parse a .tfvars file and return variable name-value pairs.

        Uses hcl2 for parsing. Single-element lists are unwrapped
        (hcl2 wraps scalar values in lists).

        Args:
            file_path: Path to the .tfvars file.

        Returns:
            Dict of variable name to value.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If file cannot be parsed.
        """
        import hcl2

        try:
            with open(file_path, "r") as f:
                parsed = hcl2.load(f)
        except FileNotFoundError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to parse tfvars file: {e}")

        # Unwrap single-element lists (hcl2 quirk)
        result = {}
        for key, value in parsed.items():
            result[key] = TfvarsHandler._unwrap(value)
        return result

    @staticmethod
    def write_tfvars(
        file_path: str,
        values: dict[str, Any],
        sensitive_names: Optional[set[str]] = None,
    ) -> None:
        """
        Write variable values to a .tfvars file in HCL format.

        Sensitive variables are excluded from the output.

        Args:
            file_path: Path to write the .tfvars file.
            values: Dict of variable name to value.
            sensitive_names: Set of variable names to exclude.
        """
        sensitive_names = sensitive_names or set()

        lines = []
        for name, value in sorted(values.items()):
            if name in sensitive_names:
                continue
            formatted = TfvarsHandler._format_value(value)
            lines.append(f'{name} = {formatted}')

        with open(file_path, "w") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")

    @staticmethod
    def _unwrap(value: Any) -> Any:
        """Unwrap a value that may be wrapped in a single-element list by hcl2."""
        if isinstance(value, list) and len(value) == 1:
            return value[0]
        return value

    @staticmethod
    def _format_value(value: Any) -> str:
        """Format a Python value as an HCL literal."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Escape backslashes and quotes
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        else:
            # For complex types, use JSON-like representation
            import json
            return json.dumps(value)
