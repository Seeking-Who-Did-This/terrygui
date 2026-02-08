"""
Tests for security module - InputSanitizer.
"""

import os
import pytest

from terrygui.security import InputSanitizer, SecurityError


def test_sanitize_variable_name_valid():
    """Test valid variable names are accepted."""
    valid_names = [
        "region",
        "instance_type",
        "aws_access_key",
        "_private_key",
        "var-with-hyphens",
        "MixedCase123",
    ]
    
    for name in valid_names:
        result = InputSanitizer.sanitize_variable_name(name)
        assert result == name


def test_sanitize_variable_name_invalid():
    """Test invalid variable names raise SecurityError."""
    invalid_names = [
        "",  # Empty
        "123invalid",  # Starts with digit
        "has spaces",  # Contains spaces
        "has@symbol",  # Invalid character
        "has.dot",  # Invalid character
        "-starts-with-hyphen",  # Starts with hyphen
    ]
    
    for name in invalid_names:
        with pytest.raises(SecurityError):
            InputSanitizer.sanitize_variable_name(name)


def test_sanitize_variable_name_too_long():
    """Test that extremely long names are rejected."""
    long_name = "a" * 500
    
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_variable_name(long_name)


def test_sanitize_variable_value_blocks_shell_chars():
    """Test that shell metacharacters are blocked."""
    dangerous_values = [
        "value;rm -rf /",
        "value|cat /etc/passwd",
        "value&background_task",
        "value`whoami`",
        "value$HOME",
        "value\\escape",
    ]
    
    for value in dangerous_values:
        with pytest.raises(SecurityError):
            InputSanitizer.sanitize_variable_value(value, "string")


def test_sanitize_variable_value_allows_safe_chars():
    """Test that safe characters are allowed."""
    safe_values = [
        "us-east-1",
        "t3.micro",
        "192.168.1.1",
        "/path/to/file",
        "value:with:colons",
        "key=value",
    ]
    
    for value in safe_values:
        result = InputSanitizer.sanitize_variable_value(value, "string")
        assert result == value


def test_sanitize_variable_value_bool():
    """Test boolean value sanitization."""
    assert InputSanitizer.sanitize_variable_value(True, "bool") == "true"
    assert InputSanitizer.sanitize_variable_value(False, "bool") == "false"
    assert InputSanitizer.sanitize_variable_value("true", "bool") == "true"
    assert InputSanitizer.sanitize_variable_value("false", "bool") == "false"


def test_sanitize_variable_value_number():
    """Test number value sanitization."""
    assert InputSanitizer.sanitize_variable_value(42, "number") == "42"
    assert InputSanitizer.sanitize_variable_value(3.14, "number") == "3.14"
    assert InputSanitizer.sanitize_variable_value("123", "number") == "123"
    
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_variable_value("not_a_number", "number")


def test_sanitize_workspace_name_valid():
    """Test valid workspace names."""
    valid_names = [
        "default",
        "production",
        "dev-environment",
        "test_workspace",
        "env123",
    ]
    
    for name in valid_names:
        result = InputSanitizer.sanitize_workspace_name(name)
        assert result == name


def test_sanitize_workspace_name_invalid():
    """Test invalid workspace names."""
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_workspace_name("")
    
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_workspace_name("-starts-with-hyphen")
    
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_workspace_name("has spaces")
    
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_workspace_name("has@symbol")


def test_sanitize_path_requires_existing():
    """Test that path must exist."""
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_path("/nonexistent/path")


def test_sanitize_path_requires_directory(tmp_path):
    """Test that path must be a directory, not a file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")
    
    with pytest.raises(SecurityError):
        InputSanitizer.sanitize_path(str(test_file))


def test_sanitize_path_allows_home_directory():
    """Test that paths in home directory are allowed."""
    home_dir = os.path.expanduser("~")
    result = InputSanitizer.sanitize_path(home_dir)
    assert os.path.isabs(result)


def test_is_safe_command_arg():
    """Test command argument safety check."""
    assert InputSanitizer.is_safe_command_arg("normal_value") is True
    assert InputSanitizer.is_safe_command_arg("value-with-hyphens") is True
    assert InputSanitizer.is_safe_command_arg("value\x00with_null") is False
    assert InputSanitizer.is_safe_command_arg("a" * 20000) is False
