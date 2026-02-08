"""
Project management for TerryGUI.

This module manages project-specific state stored in .tfgui files,
including last workspace, variable values, and UI state.
"""

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    Manages project-specific state and persistence.
    
    State is stored in .tfgui file within the project directory.
    This file is automatically added to .gitignore.
    """
    
    TFGUI_FILENAME = ".tfgui"
    GITIGNORE_FILENAME = ".gitignore"
    
    def __init__(self, project_path: str):
        """
        Initialize project manager.
        
        Args:
            project_path: Absolute path to Terraform project
        """
        self.project_path = project_path
        self.tfgui_file = os.path.join(project_path, self.TFGUI_FILENAME)
        self._state: Dict[str, Any] = self._get_default_state()
    
    @staticmethod
    def _get_default_state() -> Dict[str, Any]:
        """
        Get default project state structure.
        
        Returns:
            Default state dictionary
        """
        return {
            "version": "1.0",
            "last_workspace": "default",
            "last_opened": None,
            "variables": {},  # Non-sensitive variable values
            "ui_state": {
                "debug_output_expanded": False,
            }
        }
    
    def load(self) -> bool:
        """
        Load project state from .tfgui file.
        
        If file doesn't exist, uses default state.
        
        Returns:
            True if loaded successfully, False if using defaults
        """
        if not os.path.exists(self.tfgui_file):
            logger.info(f"No .tfgui file found at {self.tfgui_file}, using defaults")
            self._state = self._get_default_state()
            return False
        
        try:
            with open(self.tfgui_file, 'r', encoding='utf-8') as f:
                loaded_state = json.load(f)
            
            # Merge with defaults (in case structure changed)
            self._state = self._get_default_state()
            self._deep_update(self._state, loaded_state)
            
            logger.info(f"Loaded project state from {self.tfgui_file}")
            return True
        
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load .tfgui file: {e}, using defaults")
            self._state = self._get_default_state()
            return False
    
    def save(self):
        """
        Save current state to .tfgui file.
        
        Also ensures .tfgui is added to .gitignore.
        """
        # Update last_opened timestamp
        self._state["last_opened"] = datetime.now().isoformat()
        
        try:
            with open(self.tfgui_file, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, indent=2)
            
            logger.info(f"Saved project state to {self.tfgui_file}")
            
            # Ensure .gitignore includes .tfgui
            self._ensure_gitignore()
        
        except IOError as e:
            logger.error(f"Failed to save .tfgui file: {e}")
    
    def _ensure_gitignore(self):
        """
        Ensure .tfgui is added to project's .gitignore file.
        
        Creates .gitignore if it doesn't exist.
        Appends .tfgui entry if not already present.
        """
        gitignore_path = os.path.join(self.project_path, self.GITIGNORE_FILENAME)
        
        # Check if .gitignore exists and contains .tfgui
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check if .tfgui is already in gitignore
                if '.tfgui' in content:
                    return  # Already present
                
                # Append .tfgui
                with open(gitignore_path, 'a', encoding='utf-8') as f:
                    # Ensure newline before our entry
                    if not content.endswith('\n'):
                        f.write('\n')
                    f.write('# TerryGUI project state (user-specific)\n')
                    f.write('.tfgui\n')
                
                logger.info("Added .tfgui to .gitignore")
            
            except IOError as e:
                logger.error(f"Failed to update .gitignore: {e}")
        
        else:
            # Create new .gitignore
            try:
                with open(gitignore_path, 'w', encoding='utf-8') as f:
                    f.write('# TerryGUI project state (user-specific)\n')
                    f.write('.tfgui\n')
                
                logger.info("Created .gitignore with .tfgui entry")
            
            except IOError as e:
                logger.error(f"Failed to create .gitignore: {e}")
    
    def get_last_workspace(self) -> str:
        """
        Get the last active workspace for this project.
        
        Returns:
            Workspace name (defaults to "default")
        """
        return self._state.get("last_workspace", "default")
    
    def set_last_workspace(self, workspace: str):
        """
        Set the last active workspace.
        
        Args:
            workspace: Workspace name
        """
        self._state["last_workspace"] = workspace
    
    def get_variable_value(self, var_name: str) -> Optional[Any]:
        """
        Get saved variable value (non-sensitive only).
        
        Args:
            var_name: Variable name
            
        Returns:
            Saved value or None if not saved
        """
        return self._state.get("variables", {}).get(var_name, None)
    
    def set_variable_value(self, var_name: str, value: Any, sensitive: bool = False):
        """
        Set variable value.
        
        Sensitive variables are NOT saved (security policy).
        
        Args:
            var_name: Variable name
            value: Variable value
            sensitive: If True, value is NOT persisted
        """
        if sensitive:
            # Never persist sensitive variables
            return
        
        if "variables" not in self._state:
            self._state["variables"] = {}
        
        self._state["variables"][var_name] = value
    
    def get_ui_state(self, key: str, default: Any = None) -> Any:
        """
        Get UI state value.
        
        Args:
            key: State key
            default: Default value if not found
            
        Returns:
            State value or default
        """
        return self._state.get("ui_state", {}).get(key, default)
    
    def set_ui_state(self, key: str, value: Any):
        """
        Set UI state value.
        
        Args:
            key: State key
            value: State value
        """
        if "ui_state" not in self._state:
            self._state["ui_state"] = {}
        
        self._state["ui_state"][key] = value
    
    @staticmethod
    def _deep_update(base: dict, updates: dict):
        """
        Recursively update base dict with values from updates dict.
        
        Args:
            base: Dictionary to update
            updates: Dictionary with new values
        """
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ProjectManager._deep_update(base[key], value)
            else:
                base[key] = value
