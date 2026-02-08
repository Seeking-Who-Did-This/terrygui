"""
Tests for TerraformParser.
"""

import os
import pytest
from pathlib import Path

from terrygui.core import TerraformParser, TerraformVariable


@pytest.fixture
def simple_project_path():
    """Path to simple test fixture."""
    return os.path.join(os.path.dirname(__file__), "fixtures", "simple")


def test_parser_finds_variables(simple_project_path):
    """Test that parser finds all variables in simple project."""
    parser = TerraformParser(simple_project_path)
    variables = parser.parse_variables()
    
    assert len(variables) == 4
    var_names = [v.name for v in variables]
    assert "region" in var_names
    assert "instance_type" in var_names
    assert "enable_monitoring" in var_names
    assert "api_key" in var_names


def test_parser_detects_sensitive(simple_project_path):
    """Test that parser correctly identifies sensitive variables."""
    parser = TerraformParser(simple_project_path)
    variables = parser.parse_variables()
    
    api_key_var = next((v for v in variables if v.name == "api_key"), None)
    assert api_key_var is not None
    assert api_key_var.sensitive is True


def test_parser_detects_required(simple_project_path):
    """Test that parser identifies required variables (no default)."""
    parser = TerraformParser(simple_project_path)
    variables = parser.parse_variables()
    
    api_key_var = next((v for v in variables if v.name == "api_key"), None)
    assert api_key_var is not None
    assert api_key_var.is_required() is True
    
    region_var = next((v for v in variables if v.name == "region"), None)
    assert region_var is not None
    assert region_var.is_required() is False


def test_parser_extracts_defaults(simple_project_path):
    """Test that parser extracts default values."""
    parser = TerraformParser(simple_project_path)
    variables = parser.parse_variables()
    
    region_var = next((v for v in variables if v.name == "region"), None)
    assert region_var is not None
    assert region_var.default == "us-east-1"
    
    enable_monitoring_var = next((v for v in variables if v.name == "enable_monitoring"), None)
    assert enable_monitoring_var is not None
    assert enable_monitoring_var.default is False


def test_parser_extracts_types(simple_project_path):
    """Test that parser extracts variable types."""
    parser = TerraformParser(simple_project_path)
    variables = parser.parse_variables()
    
    region_var = next((v for v in variables if v.name == "region"), None)
    assert region_var is not None
    assert "string" in region_var.type
    
    enable_monitoring_var = next((v for v in variables if v.name == "enable_monitoring"), None)
    assert enable_monitoring_var is not None
    assert "bool" in enable_monitoring_var.type


def test_parser_handles_empty_directory(tmp_path):
    """Test parser handles directory with no .tf files."""
    parser = TerraformParser(str(tmp_path))
    variables = parser.parse_variables()
    
    assert len(variables) == 0


def test_parser_syntax_validation(simple_project_path):
    """Test that parser can validate syntax."""
    parser = TerraformParser(simple_project_path)
    is_valid, error = parser.validate_syntax()
    
    assert is_valid is True
    assert error is None
