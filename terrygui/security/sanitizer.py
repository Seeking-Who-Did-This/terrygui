"""
Input sanitization and validation for TerryGUI.

This module provides secure input validation to prevent:
- Path traversal attacks
- Command injection
- Invalid Terraform variable names/values
"""

import os
import re
import json
from pathlib import Path
from typing import Any, Optional


class SecurityError(Exception):
    """Raised when a security validation fails."""
    pass


class InputSanitizer:
    """
    Provides input validation and sanitization methods.
    
    All methods raise SecurityError if validation fails.
    """
    
    # Terraform variable name pattern: must start with letter/underscore,
    # can contain letters, digits, underscores, hyphens
    VARIABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_-]*$')
    
    # Maximum lengths to prevent resource exhaustion
    MAX_VARIABLE_NAME_LENGTH = 255
    MAX_VARIABLE_VALUE_LENGTH = 4096  # Increased for complex values
    MAX_WORKSPACE_NAME_LENGTH = 90    # Terraform limit
    
    # Terraform variable value: allow most characters except shell metacharacters
    # Allow: alphanumeric, spaces, common punctuation, path separators
    # Block: shell metacharacters that could cause injection
    BLOCKED_VALUE_CHARS = set(';|&$`\\"\n\r')
    
    @staticmethod
    def sanitize_path(path: str) -> str:
        """
        Validate and normalize a file system path.
        
        Security checks:
        - Resolves to absolute path
        - Must be within allowed directories (user home or /opt)
        - Must exist and be a directory
        - No symbolic link traversal outside allowed paths
        
        Args:
            path: Path to validate
            
        Returns:
            Normalized absolute path
            
        Raises:
            SecurityError: If path is unsafe
        """
        if not path:
            raise SecurityError("Path cannot be empty")
        
        # Resolve to absolute path, following symlinks
        try:
            abs_path = os.path.realpath(os.path.expanduser(path))
        except (OSError, ValueError) as e:
            raise SecurityError(f"Invalid path: {e}")
        
        # Check if path exists
        if not os.path.exists(abs_path):
            raise SecurityError(f"Path does not exist: {path}")
        
        # Must be a directory
        if not os.path.isdir(abs_path):
            raise SecurityError(f"Path is not a directory: {path}")
        
        # Check if within allowed directories
        home_dir = os.path.expanduser("~")
        allowed_prefixes = [
            home_dir,
            "/opt/terraform",  # Example: system-wide terraform projects
            "/tmp/terraform",  # Temporary terraform work
        ]
        
        if not any(abs_path.startswith(prefix) for prefix in allowed_prefixes):
            raise SecurityError(
                f"Path must be within home directory or allowed locations: {path}"
            )
        
        return abs_path
    
    @staticmethod
    def sanitize_variable_name(name: str) -> str:
        """
        Validate Terraform variable name.
        
        Rules:
        - Must start with letter or underscore
        - Can contain letters, digits, underscores, hyphens
        - Max length: 255 characters
        
        Args:
            name: Variable name to validate
            
        Returns:
            Validated variable name (unchanged if valid)
            
        Raises:
            SecurityError: If name is invalid
        """
        if not name:
            raise SecurityError("Variable name cannot be empty")
        
        if len(name) > InputSanitizer.MAX_VARIABLE_NAME_LENGTH:
            raise SecurityError(
                f"Variable name too long (max {InputSanitizer.MAX_VARIABLE_NAME_LENGTH})"
            )
        
        if not InputSanitizer.VARIABLE_NAME_PATTERN.match(name):
            raise SecurityError(
                f"Invalid variable name '{name}': must start with letter/underscore, "
                "contain only letters, digits, underscores, hyphens"
            )
        
        return name
    
    @staticmethod
    def sanitize_variable_value(value: Any, var_type: str = "string") -> str:
        """
        Validate and convert variable value to appropriate type.
        
        Security: Prevents injection through type coercion and validates format.
        
        Args:
            value: Value to validate
            var_type: Terraform type (string, number, bool, list, map)
            
        Returns:
            String representation suitable for terraform -var argument
            
        Raises:
            SecurityError: If value is unsafe or invalid for type
        """
        if value is None:
            return ""
        
        # Convert to string for validation
        str_value = str(value)
        
        # Length check
        if len(str_value) > InputSanitizer.MAX_VARIABLE_VALUE_LENGTH:
            raise SecurityError(
                f"Variable value too long (max {InputSanitizer.MAX_VARIABLE_VALUE_LENGTH})"
            )
        
        # Type-specific validation
        if var_type == "bool":
            if isinstance(value, bool):
                return "true" if value else "false"
            if str_value.lower() in ("true", "false", "1", "0"):
                return "true" if str_value.lower() in ("true", "1") else "false"
            raise SecurityError(f"Invalid boolean value: {value}")
        
        elif var_type == "number":
            try:
                # Validate it's a number
                float(str_value)
                return str_value
            except ValueError:
                raise SecurityError(f"Invalid number value: {value}")
        
        elif var_type in ("list", "map", "object"):
            # For complex types, validate as JSON
            try:
                if isinstance(value, str):
                    json.loads(value)
                    return value
                else:
                    return json.dumps(value)
            except (json.JSONDecodeError, TypeError) as e:
                raise SecurityError(f"Invalid JSON for {var_type}: {e}")
        
        else:  # string or default
            # Check for blocked characters (shell metacharacters)
            blocked_found = InputSanitizer.BLOCKED_VALUE_CHARS.intersection(str_value)
            if blocked_found:
                raise SecurityError(
                    f"Value contains forbidden characters: {blocked_found}"
                )
            
            return str_value
    
    @staticmethod
    def sanitize_workspace_name(name: str) -> str:
        """
        Validate Terraform workspace name.
        
        Rules:
        - Alphanumeric, hyphens, underscores only
        - Max length: 90 characters (Terraform limit)
        - Cannot be empty
        - Cannot start with hyphen
        
        Args:
            name: Workspace name to validate
            
        Returns:
            Validated workspace name (unchanged if valid)
            
        Raises:
            SecurityError: If name is invalid
        """
        if not name:
            raise SecurityError("Workspace name cannot be empty")
        
        if len(name) > InputSanitizer.MAX_WORKSPACE_NAME_LENGTH:
            raise SecurityError(
                f"Workspace name too long (max {InputSanitizer.MAX_WORKSPACE_NAME_LENGTH})"
            )
        
        if name.startswith("-"):
            raise SecurityError("Workspace name cannot start with hyphen")
        
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise SecurityError(
                f"Invalid workspace name '{name}': only alphanumeric, hyphens, "
                "underscores allowed"
            )
        
        return name
    
    @staticmethod
    def is_safe_command_arg(arg: str) -> bool:
        """
        Check if a command argument is safe to pass to subprocess.
        
        This is a defense-in-depth check. We should always use shell=False,
        but this adds an extra layer of validation.
        
        Args:
            arg: Command argument to check
            
        Returns:
            True if safe, False otherwise
        """
        # Check for null bytes (can cause command injection in some cases)
        if '\x00' in arg:
            return False
        
        # Check for extremely long arguments (potential DoS)
        if len(arg) > 10000:
            return False
        
        return True
