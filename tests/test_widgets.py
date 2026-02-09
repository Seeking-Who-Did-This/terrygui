"""Tests for Phase 2 UI widgets (VariableInputWidget, OutputViewerWidget).

These tests use pytest-qt where Qt is available, and pure unit tests otherwise.
All tests are designed to work without a running Terraform installation.
"""

import pytest
from unittest.mock import MagicMock, patch

from terrygui.core.terraform_parser import TerraformVariable

# Guard: skip Qt-dependent tests if PySide6 is not importable
# (CI without Qt system libs). Pure logic tests always run.
try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

needs_qt = pytest.mark.skipif(not _HAS_QT, reason="PySide6 not available")


# ---------------------------------------------------------------------------
# VariableInputWidget tests (pure logic, no Qt event loop needed)
# ---------------------------------------------------------------------------

class TestVariableInputWidget:
    """Tests that exercise VariableInputWidget logic via its public API."""

    @needs_qt
    def test_string_variable_default(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariableInputWidget
        var = TerraformVariable(name="region", type="string", default="us-east-1")
        widget = VariableInputWidget(var)
        qtbot.addWidget(widget)
        assert widget.get_value() == "us-east-1"
        assert widget.is_valid()

    @needs_qt
    def test_required_variable_empty_invalid(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariableInputWidget
        var = TerraformVariable(name="api_key", type="string")  # no default → required
        widget = VariableInputWidget(var)
        qtbot.addWidget(widget)
        assert not widget.is_valid()

    @needs_qt
    def test_bool_variable(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariableInputWidget
        var = TerraformVariable(name="enabled", type="bool", default=True)
        widget = VariableInputWidget(var)
        qtbot.addWidget(widget)
        assert widget.get_value() is True
        widget.set_value(False)
        assert widget.get_value() is False

    @needs_qt
    def test_number_variable(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariableInputWidget
        var = TerraformVariable(name="count", type="number", default=3)
        widget = VariableInputWidget(var)
        qtbot.addWidget(widget)
        assert widget.get_value() == "3"

    @needs_qt
    def test_sensitive_variable_has_password_mode(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariableInputWidget
        from PySide6.QtWidgets import QLineEdit
        var = TerraformVariable(name="secret", type="string", sensitive=True)
        widget = VariableInputWidget(var)
        qtbot.addWidget(widget)
        assert widget._input.echoMode() == QLineEdit.EchoMode.Password

    @needs_qt
    def test_set_value_string(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariableInputWidget
        var = TerraformVariable(name="name", type="string")
        widget = VariableInputWidget(var)
        qtbot.addWidget(widget)
        widget.set_value("hello")
        assert widget.get_value() == "hello"

    @needs_qt
    def test_list_variable(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariableInputWidget
        var = TerraformVariable(name="tags", type="list", default=["a", "b"])
        widget = VariableInputWidget(var)
        qtbot.addWidget(widget)
        # Default should be JSON-formatted
        val = widget.get_value()
        assert "a" in val and "b" in val


# ---------------------------------------------------------------------------
# VariablesPanel tests
# ---------------------------------------------------------------------------

class TestVariablesPanel:
    @needs_qt
    def test_load_variables(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariablesPanel
        panel = VariablesPanel()
        qtbot.addWidget(panel)

        variables = [
            TerraformVariable(name="region", type="string", default="us-east-1"),
            TerraformVariable(name="enabled", type="bool", default=True),
        ]
        panel.load_variables(variables)
        assert len(panel._widgets) == 2
        assert panel.all_valid()

    @needs_qt
    def test_load_with_saved_values(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariablesPanel
        panel = VariablesPanel()
        qtbot.addWidget(panel)

        variables = [
            TerraformVariable(name="region", type="string", default="us-east-1"),
        ]
        panel.load_variables(variables, saved_values={"region": "eu-west-1"})
        assert panel._widgets["region"].get_value() == "eu-west-1"

    @needs_qt
    def test_clear(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariablesPanel
        panel = VariablesPanel()
        qtbot.addWidget(panel)

        variables = [TerraformVariable(name="x", type="string", default="val")]
        panel.load_variables(variables)
        assert len(panel._widgets) == 1
        panel.clear()
        assert len(panel._widgets) == 0

    @needs_qt
    def test_get_non_sensitive_values(self, qtbot):
        from terrygui.ui.widgets.variable_input import VariablesPanel
        panel = VariablesPanel()
        qtbot.addWidget(panel)

        variables = [
            TerraformVariable(name="region", type="string", default="us-east-1"),
            TerraformVariable(name="secret", type="string", sensitive=True),
        ]
        panel.load_variables(variables)
        panel._widgets["secret"].set_value("my_secret")

        non_sensitive = panel.get_non_sensitive_values()
        assert "region" in non_sensitive
        assert "secret" not in non_sensitive


# ---------------------------------------------------------------------------
# OutputViewerWidget tests
# ---------------------------------------------------------------------------

class TestOutputViewerWidget:
    @needs_qt
    def test_append_output(self, qtbot):
        from terrygui.ui.widgets.output_viewer import OutputViewerWidget
        viewer = OutputViewerWidget()
        qtbot.addWidget(viewer)
        viewer.append_output("Hello world")
        assert "Hello world" in viewer.get_text()
        assert viewer.line_count() == 1

    @needs_qt
    def test_append_multiple_lines(self, qtbot):
        from terrygui.ui.widgets.output_viewer import OutputViewerWidget
        viewer = OutputViewerWidget()
        qtbot.addWidget(viewer)
        viewer.append_output("line 1")
        viewer.append_output("line 2")
        viewer.append_output("line 3")
        assert viewer.line_count() == 3

    @needs_qt
    def test_clear(self, qtbot):
        from terrygui.ui.widgets.output_viewer import OutputViewerWidget
        viewer = OutputViewerWidget()
        qtbot.addWidget(viewer)
        viewer.append_output("something")
        viewer.clear()
        assert viewer.get_text() == ""
        assert viewer.line_count() == 0

    @needs_qt
    def test_max_lines_enforced(self, qtbot):
        from terrygui.ui.widgets.output_viewer import OutputViewerWidget
        viewer = OutputViewerWidget()
        viewer.MAX_LINES = 5  # Override for test speed
        qtbot.addWidget(viewer)
        for i in range(10):
            viewer.append_output(f"line {i}")
        assert viewer.line_count() == 5

    @needs_qt
    def test_ansi_color_stripped_from_plain_text(self, qtbot):
        from terrygui.ui.widgets.output_viewer import OutputViewerWidget
        viewer = OutputViewerWidget()
        qtbot.addWidget(viewer)
        viewer.append_output("\x1b[32mSuccess\x1b[0m")
        # Plain text should not contain escape codes
        plain = viewer.get_text()
        assert "\x1b" not in plain
        assert "Success" in plain
