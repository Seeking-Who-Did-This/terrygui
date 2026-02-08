"""
Terraform configuration parser.

This module parses Terraform HCL files to extract variable definitions,
outputs, and other configuration information.
"""

import glob
import os
import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple
import hcl2

logger = logging.getLogger(__name__)


@dataclass
class TerraformVariable:
    """
    Represents a Terraform variable definition.
    
    Attributes:
        name: Variable name
        type: Variable type (string, number, bool, list, map, etc.)
        default: Default value (None if no default)
        description: Human-readable description
        sensitive: Whether variable is marked as sensitive
        validation: Custom validation rules from HCL
    """
    name: str
    type: str = "string"
    default: Optional[Any] = None
    description: str = ""
    sensitive: bool = False
    validation: Optional[dict] = None
    
    def is_required(self) -> bool:
        """
        Check if variable is required (has no default).
        
        Returns:
            True if variable must be provided
        """
        return self.default is None
    
    def __repr__(self) -> str:
        return (
            f"TerraformVariable(name='{self.name}', type='{self.type}', "
            f"required={self.is_required()}, sensitive={self.sensitive})"
        )


class TerraformParser:
    """
    Parser for Terraform configuration files.
    
    Extracts variable definitions, outputs, and validates syntax.
    """
    
    def __init__(self, project_path: str):
        """
        Initialize parser for a Terraform project.
        
        Args:
            project_path: Path to Terraform project directory
        """
        self.project_path = project_path
        self._variables: Optional[List[TerraformVariable]] = None
        self._outputs: Optional[List[dict]] = None
    
    def parse_variables(self) -> List[TerraformVariable]:
        """
        Parse all .tf files in project for variable blocks.
        
        Returns:
            List of TerraformVariable objects
            
        Raises:
            IOError: If unable to read files
        """
        if self._variables is not None:
            return self._variables
        
        variables = []
        
        # Find all .tf files in project directory
        tf_files = glob.glob(os.path.join(self.project_path, "*.tf"))
        
        if not tf_files:
            logger.warning(f"No .tf files found in {self.project_path}")
            self._variables = []
            return self._variables
        
        logger.info(f"Found {len(tf_files)} Terraform files")
        
        for tf_file in tf_files:
            try:
                variables.extend(self._parse_file_variables(tf_file))
            except Exception as e:
                logger.error(f"Failed to parse {tf_file}: {e}")
                # Continue with other files
        
        self._variables = variables
        logger.info(f"Parsed {len(variables)} variables")
        
        return self._variables
    
    def _parse_file_variables(self, tf_file: str) -> List[TerraformVariable]:
        """
        Parse variables from a single .tf file.
        
        Args:
            tf_file: Path to .tf file
            
        Returns:
            List of TerraformVariable objects from this file
        """
        variables = []
        
        try:
            with open(tf_file, 'r', encoding='utf-8') as f:
                parsed = hcl2.load(f)
        except Exception as e:
            logger.error(f"HCL parse error in {tf_file}: {e}")
            return variables
        
        # Extract variable blocks
        if 'variable' not in parsed:
            return variables
        
        for var_block in parsed['variable']:
            for var_name, var_config in var_block.items():
                try:
                    variable = self._create_variable(var_name, var_config)
                    variables.append(variable)
                except Exception as e:
                    logger.error(f"Failed to create variable '{var_name}': {e}")
        
        return variables
    
    def _create_variable(self, name: str, config: dict) -> TerraformVariable:
        """
        Create TerraformVariable from parsed HCL config.
        
        Args:
            name: Variable name
            config: Parsed variable configuration dict
            
        Returns:
            TerraformVariable object
        """
        # Extract type (default to string if not specified)
        var_type = self._extract_type(config.get('type', 'string'))
        
        # Extract default value
        default = config.get('default', [None])[0] if 'default' in config else None
        
        # Extract description
        description = config.get('description', [''])[0] if 'description' in config else ''
        
        # Extract sensitive flag
        sensitive = config.get('sensitive', [False])[0] if 'sensitive' in config else False
        
        # Extract validation (if present)
        validation = config.get('validation', None)
        
        return TerraformVariable(
            name=name,
            type=var_type,
            default=default,
            description=description,
            sensitive=sensitive,
            validation=validation
        )
    
    def _extract_type(self, type_value: Any) -> str:
        """
        Extract and normalize Terraform type.
        
        Args:
            type_value: Type value from HCL (can be string or complex structure)
            
        Returns:
            Normalized type string
        """
        if isinstance(type_value, str):
            return type_value
        elif isinstance(type_value, list) and len(type_value) > 0:
            # Sometimes hcl2 returns types as lists
            return str(type_value[0])
        else:
            # For complex types, convert to string representation
            return str(type_value)
    
    def parse_outputs(self) -> List[dict]:
        """
        Parse all .tf files for output blocks.
        
        Returns:
            List of output definitions
        """
        if self._outputs is not None:
            return self._outputs
        
        outputs = []
        tf_files = glob.glob(os.path.join(self.project_path, "*.tf"))
        
        for tf_file in tf_files:
            try:
                with open(tf_file, 'r', encoding='utf-8') as f:
                    parsed = hcl2.load(f)
                
                if 'output' in parsed:
                    for output_block in parsed['output']:
                        for output_name, output_config in output_block.items():
                            outputs.append({
                                'name': output_name,
                                'value': output_config.get('value', [None])[0],
                                'description': output_config.get('description', [''])[0],
                                'sensitive': output_config.get('sensitive', [False])[0],
                            })
            except Exception as e:
                logger.error(f"Failed to parse outputs from {tf_file}: {e}")
        
        self._outputs = outputs
        return self._outputs
    
    def validate_syntax(self) -> Tuple[bool, Optional[str]]:
        """
        Validate Terraform syntax by attempting to parse all files.
        
        Returns:
            Tuple of (is_valid, error_message)
            If valid, error_message is None
        """
        tf_files = glob.glob(os.path.join(self.project_path, "*.tf"))
        
        if not tf_files:
            return False, "No .tf files found in project"
        
        for tf_file in tf_files:
            try:
                with open(tf_file, 'r', encoding='utf-8') as f:
                    hcl2.load(f)
            except Exception as e:
                return False, f"Syntax error in {os.path.basename(tf_file)}: {str(e)}"
        
        return True, None
