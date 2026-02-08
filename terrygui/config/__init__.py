"""
Configuration management for TerryGUI.

This module handles application settings, defaults, and persistence.
"""

from .settings import Settings
from .defaults import DEFAULT_SETTINGS

__all__ = ["Settings", "DEFAULT_SETTINGS"]
