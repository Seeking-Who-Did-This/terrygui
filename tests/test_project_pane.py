"""Tests for ProjectPane widget.

Follows the same guard/pattern as test_widgets.py.
"""

import pytest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

needs_qt = pytest.mark.skipif(not _HAS_QT, reason="PySide6 not available")


class TestProjectPane:

    @needs_qt
    def test_pane_initial_state(self, qtbot, mock_settings):
        """No project loaded → all operation buttons disabled."""
        from terrygui.ui.widgets.project_pane import ProjectPane

        pane = ProjectPane(mock_settings)
        qtbot.addWidget(pane)

        assert pane.current_project_path is None
        assert not pane.init_button.isEnabled()
        assert not pane.validate_button.isEnabled()
        assert not pane.plan_button.isEnabled()
        assert not pane.apply_button.isEnabled()
        assert not pane.destroy_button.isEnabled()
        assert not pane.cancel_button.isEnabled()

    @needs_qt
    def test_pane_load_invalid_path(self, qtbot, tmp_path, mock_settings):
        """Loading a non-Terraform directory raises ValueError."""
        from terrygui.ui.widgets.project_pane import ProjectPane

        pane = ProjectPane(mock_settings)
        qtbot.addWidget(pane)

        # tmp_path is an empty dir — no .tf files.
        # Patch sanitize_path so the CI temp dir isn't rejected by the
        # allowlist before we reach the "no .tf files" check.
        with patch("terrygui.ui.widgets.project_pane.InputSanitizer.sanitize_path",
                   return_value=str(tmp_path)):
            with pytest.raises(ValueError, match="Terraform project"):
                pane.load_project(str(tmp_path))

    @needs_qt
    def test_pane_status_message_signal(self, qtbot, tmp_path, mock_settings):
        """status_message signal is emitted after a successful project load."""
        from terrygui.ui.widgets.project_pane import ProjectPane

        # Create a minimal .tf file so the directory passes validation
        (tmp_path / "main.tf").write_text('variable "region" {}')

        pane = ProjectPane(mock_settings)
        qtbot.addWidget(pane)

        received = []
        pane.status_message.connect(received.append)

        with patch("terrygui.ui.widgets.project_pane.InputSanitizer.sanitize_path",
                   return_value=str(tmp_path)), \
             patch("terrygui.ui.widgets.project_pane.TerraformRunner"), \
             patch("terrygui.ui.widgets.project_pane.WorkspaceManager"), \
             patch("terrygui.ui.widgets.project_pane.StateManager"):
            pane.load_project(str(tmp_path))

        assert any("Project loaded" in m for m in received), \
            f"Expected 'Project loaded' in signals, got: {received}"

    @needs_qt
    def test_pane_save_state_no_project(self, qtbot, mock_settings):
        """save_state() is a safe no-op when no project is loaded."""
        from terrygui.ui.widgets.project_pane import ProjectPane

        pane = ProjectPane(mock_settings)
        qtbot.addWidget(pane)

        # Should not raise
        pane.save_state()
