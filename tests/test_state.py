"""Tests for Phase 5 state viewing.

Tests for StateManager and StateViewerWidget.
All tests mock subprocess so no real Terraform installation is needed.
"""

import pytest
from unittest.mock import MagicMock, patch

from terrygui.core.state_manager import StateManager, StateResource, StateSummary
from terrygui.security.sanitizer import SecurityError

# Guard: skip Qt-dependent tests if PySide6 is not importable
try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

needs_qt = pytest.mark.skipif(not _HAS_QT, reason="PySide6 not available")


# ---------------------------------------------------------------------------
# StateManager tests (pure logic, mock subprocess)
# ---------------------------------------------------------------------------

class TestStateManager:
    """Tests for StateManager command construction and parsing."""

    def _make_manager(self, tmp_path):
        (tmp_path / "main.tf").write_text("")
        return StateManager(str(tmp_path), terraform_binary="terraform")

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_list_resources_parses_output(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="aws_instance.web\naws_s3_bucket.data\naws_iam_role.lambda_role\n",
            stderr="",
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.list_resources()

        assert len(result) == 3
        assert result[0].address == "aws_instance.web"
        assert result[0].type == "aws_instance"
        assert result[0].name == "web"
        assert result[1].address == "aws_s3_bucket.data"
        assert result[1].type == "aws_s3_bucket"
        assert result[1].name == "data"
        assert result[2].address == "aws_iam_role.lambda_role"
        assert result[2].type == "aws_iam_role"
        assert result[2].name == "lambda_role"

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_list_resources_empty_state(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.list_resources()
        assert result == []

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_list_resources_error(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="No state file found"
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.list_resources()
        assert result == []

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_list_resources_with_modules(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="module.vpc.aws_vpc.main\naws_instance.web\n",
            stderr="",
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.list_resources()

        assert len(result) == 2
        assert result[0].address == "module.vpc.aws_vpc.main"
        assert result[0].type == "aws_vpc"
        assert result[0].name == "main"

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_get_resource_details(self, mock_run, tmp_path):
        detail_output = '# aws_instance.web:\nresource "aws_instance" "web" {\n    ami = "ami-123"\n}\n'
        mock_run.return_value = MagicMock(
            returncode=0, stdout=detail_output, stderr=""
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.get_resource_details("aws_instance.web")

        assert "aws_instance" in result
        cmd = mock_run.call_args[0][0]
        assert "state" in cmd
        assert "show" in cmd
        assert "aws_instance.web" in cmd

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_get_resource_details_error(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not found"
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.get_resource_details("aws_instance.web")
        assert "Error" in result

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_get_outputs(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='vpc_id = "vpc-abc123"\nregion = "us-east-1"\n',
            stderr="",
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.get_outputs()

        assert "vpc_id" in result
        cmd = mock_run.call_args[0][0]
        assert "output" in cmd
        assert "-no-color" in cmd

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_get_outputs_error(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="no outputs"
        )
        mgr = self._make_manager(tmp_path)
        result = mgr.get_outputs()
        assert "Error" in result

    def test_resource_address_validation_rejects_unsafe(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        with pytest.raises(SecurityError):
            mgr.get_resource_details("$(whoami)")

    def test_resource_address_validation_rejects_semicolons(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        with pytest.raises(SecurityError):
            mgr.get_resource_details("foo; rm -rf /")

    def test_resource_address_validation_rejects_empty(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        with pytest.raises(SecurityError):
            mgr.get_resource_details("")

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_shell_false_always(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        mgr.list_resources()

        kwargs = mock_run.call_args[1]
        assert kwargs.get("shell") is False

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_chdir_flag_used(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mgr = self._make_manager(tmp_path)
        mgr.list_resources()

        cmd = mock_run.call_args[0][0]
        assert any(arg.startswith("-chdir=") for arg in cmd)

    @patch("terrygui.core.state_manager.subprocess.run")
    def test_timeout_returns_empty(self, mock_run, tmp_path):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="terraform", timeout=15)
        mgr = self._make_manager(tmp_path)
        result = mgr.list_resources()
        assert result == []

    def test_parse_address_simple(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr._parse_address("aws_instance.web") == ("aws_instance", "web")

    def test_parse_address_module(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr._parse_address("module.vpc.aws_vpc.main") == ("aws_vpc", "main")


# ---------------------------------------------------------------------------
# StateViewerWidget tests (Qt)
# ---------------------------------------------------------------------------

class TestStateViewerWidget:
    """Tests for the state viewer widget."""

    @needs_qt
    def test_starts_empty(self, qtbot):
        from terrygui.ui.widgets.state_viewer import StateViewerWidget
        viewer = StateViewerWidget()
        qtbot.addWidget(viewer)

        assert viewer._resource_list.count() == 0
        assert viewer._detail_view.toPlainText() == ""
        assert viewer._count_label.text() == "State Resources"

    @needs_qt
    def test_load_resources(self, qtbot):
        from terrygui.ui.widgets.state_viewer import StateViewerWidget
        viewer = StateViewerWidget()
        qtbot.addWidget(viewer)

        mock_mgr = MagicMock()
        mock_mgr.list_resources.return_value = [
            StateResource("aws_instance.web", "aws_instance", "web", ""),
            StateResource("aws_s3_bucket.data", "aws_s3_bucket", "data", ""),
        ]

        viewer.set_manager(mock_mgr)

        assert viewer._resource_list.count() == 2
        assert viewer._resource_list.item(0).text() == "aws_instance.web"
        assert viewer._resource_list.item(1).text() == "aws_s3_bucket.data"
        assert "2" in viewer._count_label.text()

    @needs_qt
    def test_select_resource_shows_details(self, qtbot):
        from terrygui.ui.widgets.state_viewer import StateViewerWidget
        viewer = StateViewerWidget()
        qtbot.addWidget(viewer)

        mock_mgr = MagicMock()
        mock_mgr.list_resources.return_value = [
            StateResource("aws_instance.web", "aws_instance", "web", ""),
        ]
        mock_mgr.get_resource_details.return_value = 'resource "aws_instance" "web" {\n  ami = "ami-123"\n}'

        viewer.set_manager(mock_mgr)
        viewer._resource_list.setCurrentRow(0)

        mock_mgr.get_resource_details.assert_called_once_with("aws_instance.web")
        assert "ami-123" in viewer._detail_view.toPlainText()

    @needs_qt
    def test_outputs_view(self, qtbot):
        from terrygui.ui.widgets.state_viewer import StateViewerWidget
        viewer = StateViewerWidget()
        qtbot.addWidget(viewer)

        mock_mgr = MagicMock()
        mock_mgr.list_resources.return_value = []
        mock_mgr.get_outputs.return_value = 'vpc_id = "vpc-123"'

        viewer.set_manager(mock_mgr)
        viewer._on_view_toggled(1)

        assert "vpc-123" in viewer._detail_view.toPlainText()

    @needs_qt
    def test_refresh_reloads(self, qtbot):
        from terrygui.ui.widgets.state_viewer import StateViewerWidget
        viewer = StateViewerWidget()
        qtbot.addWidget(viewer)

        mock_mgr = MagicMock()
        mock_mgr.list_resources.return_value = [
            StateResource("aws_instance.web", "aws_instance", "web", ""),
        ]

        viewer.set_manager(mock_mgr)
        assert mock_mgr.list_resources.call_count == 1

        viewer._on_refresh()
        assert mock_mgr.list_resources.call_count == 2
