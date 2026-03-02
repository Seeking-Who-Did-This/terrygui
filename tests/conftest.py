"""Shared pytest fixtures for the TerryGUI test suite."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_settings():
    """Return a minimal Settings-like mock suitable for constructing ProjectPane."""
    settings = MagicMock()
    settings.get.side_effect = lambda key, default=None: default
    settings.get_open_projects.return_value = []
    settings.get_last_project.return_value = None
    settings.get_recent_projects.return_value = []
    return settings
