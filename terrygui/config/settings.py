"""
Settings management for TerryGUI.

Handles loading, saving, and accessing application configuration.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import logging

from .defaults import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)


class Settings:
    """
    Application settings manager.
    
    Handles persistent configuration stored in user's config directory.
    Settings are stored as JSON.
    
    Path:
        Linux/macOS: ~/.config/terrygui/settings.json
        Windows: %APPDATA%\\terrygui\\settings.json
    """
    
    def __init__(self):
        """Initialize settings manager."""
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "settings.json"
        self._settings: Dict[str, Any] = {}
        self.load()
    
    @staticmethod
    def _get_config_dir() -> Path:
        """
        Get platform-specific configuration directory.
        
        Returns:
            Path to configuration directory
        """
        if os.name == 'nt':  # Windows
            base = os.environ.get('APPDATA', os.path.expanduser('~'))
            config_dir = Path(base) / 'terrygui'
        else:  # Linux/macOS
            base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            config_dir = Path(base) / 'terrygui'
        
        # Create directory if it doesn't exist
        config_dir.mkdir(parents=True, exist_ok=True)
        
        return config_dir
    
    def load(self):
        """
        Load settings from file.
        
        If file doesn't exist or is invalid, uses default settings.
        """
        if not self.config_file.exists():
            logger.info("No config file found, using defaults")
            self._settings = DEFAULT_SETTINGS.copy()
            return
        
        try:
            with open(self.config_file, 'r') as f:
                loaded_settings = json.load(f)
            
            # Merge with defaults (in case new settings were added)
            self._settings = DEFAULT_SETTINGS.copy()
            self._deep_update(self._settings, loaded_settings)
            
            logger.info(f"Loaded settings from {self.config_file}")
        
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load settings: {e}, using defaults")
            self._settings = DEFAULT_SETTINGS.copy()
    
    def save(self):
        """
        Save current settings to file.
        
        Creates parent directories if needed.
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_file, 'w') as f:
                json.dump(self._settings, f, indent=2)
            
            logger.info(f"Saved settings to {self.config_file}")
        
        except IOError as e:
            logger.error(f"Failed to save settings: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get setting value.
        
        Supports nested keys with dot notation: "window.width"
        
        Args:
            key: Setting key (use dots for nested values)
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        keys = key.split('.')
        value = self._settings
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        Set setting value.
        
        Supports nested keys with dot notation: "window.width"
        
        Args:
            key: Setting key (use dots for nested values)
            value: Value to set
        """
        keys = key.split('.')
        target = self._settings
        
        # Navigate to parent of target key
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        
        # Set the value
        target[keys[-1]] = value
    
    def add_recent_project(self, project_path: str):
        """
        Add project to recent projects list.
        
        Maintains max_recent_projects limit and removes duplicates.
        
        Args:
            project_path: Absolute path to project
        """
        recent = self.get("recent_projects", [])
        
        # Remove if already exists (to move to front)
        if project_path in recent:
            recent.remove(project_path)
        
        # Add to front
        recent.insert(0, project_path)
        
        # Trim to max length
        max_projects = self.get("max_recent_projects", 10)
        recent = recent[:max_projects]
        
        self.set("recent_projects", recent)
    
    def get_recent_projects(self) -> list:
        """
        Get list of recent project paths.
        
        Returns:
            List of absolute paths (most recent first)
        """
        return self.get("recent_projects", [])
    
    def set_last_project(self, project_path: str):
        """
        Set the last opened project path.
        
        Args:
            project_path: Absolute path to project
        """
        self.set("last_project_path", project_path)
    
    def get_last_project(self) -> Optional[str]:
        """
        Get the last opened project path.
        
        Returns:
            Project path or None
        """
        path = self.get("last_project_path", "")
        return path if path else None
    
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
                Settings._deep_update(base[key], value)
            else:
                base[key] = value
