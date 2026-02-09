"""Tests for Phase 4 workspace management.

Tests for WorkspaceManager, WorkspacePanelWidget, and WorkspaceDialog.
All tests mock subprocess so no real Terraform installation is needed.
"""

import pytest
from unittest.mock import MagicMock, patch, call

from terrygui.core.workspace_manager import WorkspaceManager, WorkspaceInfo
from terrygui.security.sanitizer import SecurityError

# Guard: skip Qt-dependent tests if PySide6 is not importable
try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

needs_qt = pytest.mark.skipif(not _HAS_QT, reason="PySide6 not available")


# ---------------------------------------------------------------------------
# WorkspaceManager tests (pure logic, mock subprocess)
# ---------------------------------------------------------------------------

class TestWorkspaceManager:
    """Tests for WorkspaceManager command construction and parsing."""

    def _make_manager(self, tmp_path):
        # Create a .tf file so the path looks valid
        (tmp_path / "main.tf").write_text("")
        return WorkspaceManager(str(tmp_path), terraform_binary="terraform")

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_list_workspaces_parses_output(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  default\n* staging\n  production\n",
            stderr="",
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.list_workspaces()

        assert len(result) == 3
        assert result[0] == WorkspaceInfo(name="default", is_current=False)
        assert result[1] == WorkspaceInfo(name="staging", is_current=True)
        assert result[2] == WorkspaceInfo(name="production", is_current=False)

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_list_workspaces_single_default(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="* default\n",
            stderr="",
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.list_workspaces()

        assert len(result) == 1
        assert result[0] == WorkspaceInfo(name="default", is_current=True)

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_list_workspaces_error_returns_default(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="some error"
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.list_workspaces()

        assert len(result) == 1
        assert result[0].name == "default"
        assert result[0].is_current is True

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_get_current_workspace(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="staging\n", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.get_current_workspace() == "staging"

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_get_current_workspace_error_returns_default(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error"
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.get_current_workspace() == "default"

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_switch_workspace(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.switch_workspace("production") is True

        cmd = mock_run.call_args[0][0]
        assert "workspace" in cmd
        assert "select" in cmd
        assert "production" in cmd

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_switch_workspace_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not found"
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.switch_workspace("nonexistent") is False

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_create_workspace(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.create_workspace("dev") is True

        cmd = mock_run.call_args[0][0]
        assert "workspace" in cmd
        assert "new" in cmd
        assert "dev" in cmd

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_create_workspace_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="already exists"
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.create_workspace("existing") is False

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_delete_workspace(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.delete_workspace("old") is True

        cmd = mock_run.call_args[0][0]
        assert "workspace" in cmd
        assert "delete" in cmd
        assert "old" in cmd
        assert "-force" not in cmd

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_delete_workspace_force(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        assert mgr.delete_workspace("old", force=True) is True

        cmd = mock_run.call_args[0][0]
        assert "-force" in cmd

    def test_create_workspace_rejects_invalid_name(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        with pytest.raises(SecurityError):
            mgr.create_workspace("bad name!")

    def test_switch_workspace_rejects_invalid_name(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        with pytest.raises(SecurityError):
            mgr.switch_workspace("../escape")

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_timeout_returns_error(self, mock_run, tmp_path):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="terraform", timeout=15)
        mgr = self._make_manager(tmp_path)
        assert mgr.get_current_workspace() == "default"

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_chdir_flag_used(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="default\n", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        mgr.get_current_workspace()

        cmd = mock_run.call_args[0][0]
        assert any(arg.startswith("-chdir=") for arg in cmd)

    @patch("terrygui.core.workspace_manager.subprocess.run")
    def test_shell_false_always(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        mgr.list_workspaces()

        kwargs = mock_run.call_args[1]
        assert kwargs.get("shell") is False


# ---------------------------------------------------------------------------
# WorkspaceDialog tests (Qt)
# ---------------------------------------------------------------------------

class TestWorkspaceDialog:
    """Tests for the workspace create/delete dialogs."""

    @needs_qt
    def test_create_dialog_starts_with_disabled_button(self, qtbot):
        from terrygui.ui.dialogs.workspace_dialog import WorkspaceDialog
        dialog = WorkspaceDialog("create")
        qtbot.addWidget(dialog)

        assert not dialog._create_button.isEnabled()

    @needs_qt
    def test_create_dialog_valid_name_enables_button(self, qtbot):
        from terrygui.ui.dialogs.workspace_dialog import WorkspaceDialog
        dialog = WorkspaceDialog("create")
        qtbot.addWidget(dialog)

        dialog._name_input.setText("staging")
        assert dialog._create_button.isEnabled()
        assert dialog._error_label.text() == ""

    @needs_qt
    def test_create_dialog_invalid_name_shows_error(self, qtbot):
        from terrygui.ui.dialogs.workspace_dialog import WorkspaceDialog
        dialog = WorkspaceDialog("create")
        qtbot.addWidget(dialog)

        dialog._name_input.setText("bad name!")
        assert not dialog._create_button.isEnabled()
        assert dialog._error_label.text() != ""

    @needs_qt
    def test_create_dialog_workspace_name(self, qtbot):
        from terrygui.ui.dialogs.workspace_dialog import WorkspaceDialog
        dialog = WorkspaceDialog("create")
        qtbot.addWidget(dialog)

        dialog._name_input.setText("  my-workspace  ")
        assert dialog.workspace_name() == "my-workspace"

    @needs_qt
    def test_delete_dialog_shows_workspace_name(self, qtbot):
        from terrygui.ui.dialogs.workspace_dialog import WorkspaceDialog
        dialog = WorkspaceDialog("delete", workspace_name_value="staging")
        qtbot.addWidget(dialog)

        assert dialog.workspace_name() == "staging"

    @needs_qt
    def test_delete_dialog_is_modal(self, qtbot):
        from terrygui.ui.dialogs.workspace_dialog import WorkspaceDialog
        dialog = WorkspaceDialog("delete", workspace_name_value="staging")
        qtbot.addWidget(dialog)

        assert dialog.isModal()


# ---------------------------------------------------------------------------
# WorkspacePanelWidget tests (Qt)
# ---------------------------------------------------------------------------

class TestWorkspacePanelWidget:
    """Tests for the workspace selector panel."""

    @needs_qt
    def test_starts_disabled(self, qtbot):
        from terrygui.ui.widgets.workspace_panel import WorkspacePanelWidget
        panel = WorkspacePanelWidget()
        qtbot.addWidget(panel)

        assert not panel.isEnabled()

    @needs_qt
    def test_set_manager_enables_and_populates(self, qtbot):
        from terrygui.ui.widgets.workspace_panel import WorkspacePanelWidget
        panel = WorkspacePanelWidget()
        qtbot.addWidget(panel)

        mock_mgr = MagicMock()
        mock_mgr.list_workspaces.return_value = [
            WorkspaceInfo("default", True),
            WorkspaceInfo("staging", False),
        ]

        panel.set_manager(mock_mgr)

        assert panel.isEnabled()
        assert panel._combo.count() == 2
        assert panel._combo.currentText() == "default"

    @needs_qt
    def test_current_workspace_default(self, qtbot):
        from terrygui.ui.widgets.workspace_panel import WorkspacePanelWidget
        panel = WorkspacePanelWidget()
        qtbot.addWidget(panel)

        assert panel.current_workspace() == "default"

    @needs_qt
    def test_delete_disabled_for_default(self, qtbot):
        from terrygui.ui.widgets.workspace_panel import WorkspacePanelWidget
        panel = WorkspacePanelWidget()
        qtbot.addWidget(panel)

        mock_mgr = MagicMock()
        mock_mgr.list_workspaces.return_value = [
            WorkspaceInfo("default", True),
        ]

        panel.set_manager(mock_mgr)
        assert not panel._delete_button.isEnabled()

    @needs_qt
    def test_refresh_updates_combo(self, qtbot):
        from terrygui.ui.widgets.workspace_panel import WorkspacePanelWidget
        panel = WorkspacePanelWidget()
        qtbot.addWidget(panel)

        mock_mgr = MagicMock()
        mock_mgr.list_workspaces.return_value = [
            WorkspaceInfo("default", True),
        ]
        panel.set_manager(mock_mgr)
        assert panel._combo.count() == 1

        # Simulate workspaces changing
        mock_mgr.list_workspaces.return_value = [
            WorkspaceInfo("default", False),
            WorkspaceInfo("staging", True),
            WorkspaceInfo("prod", False),
        ]
        panel.refresh()
        assert panel._combo.count() == 3
        assert panel._combo.currentText() == "staging"
