"""Tests for Phase 6 polish & advanced features.

Tests for TfvarsHandler, SettingsDialog, recent projects, keyboard shortcuts,
and import/export integration.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

from terrygui.core.tfvars_handler import TfvarsHandler
from terrygui.core.terraform_parser import TerraformVariable

# Guard: skip Qt-dependent tests if PySide6 is not importable
try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

needs_qt = pytest.mark.skipif(not _HAS_QT, reason="PySide6 not available")


# ---------------------------------------------------------------------------
# TfvarsHandler tests
# ---------------------------------------------------------------------------

class TestTfvarsHandlerParse:
    """Tests for TfvarsHandler.parse_tfvars()."""

    def test_parse_simple_key_value(self, tmp_path):
        tfvars = tmp_path / "test.tfvars"
        tfvars.write_text('region = "us-east-1"\nproject = "myapp"\n')
        result = TfvarsHandler.parse_tfvars(str(tfvars))
        assert result["region"] == "us-east-1"
        assert result["project"] == "myapp"

    def test_parse_complex_types(self, tmp_path):
        tfvars = tmp_path / "test.tfvars"
        tfvars.write_text(
            'tags = ["a", "b", "c"]\n'
            'enabled = true\n'
            'count = 42\n'
        )
        result = TfvarsHandler.parse_tfvars(str(tfvars))
        assert result["enabled"] is True
        assert result["count"] == 42
        # tags is a list, hcl2 may wrap it
        tags = result["tags"]
        if isinstance(tags, list) and len(tags) == 1 and isinstance(tags[0], list):
            tags = tags[0]  # double-wrapped
        assert "a" in tags

    def test_parse_empty_file(self, tmp_path):
        tfvars = tmp_path / "empty.tfvars"
        tfvars.write_text("")
        result = TfvarsHandler.parse_tfvars(str(tfvars))
        assert result == {}

    def test_parse_missing_file(self):
        with pytest.raises(FileNotFoundError):
            TfvarsHandler.parse_tfvars("/nonexistent/path/test.tfvars")

    def test_parse_bool_and_number(self, tmp_path):
        tfvars = tmp_path / "test.tfvars"
        tfvars.write_text('debug = false\nreplicas = 3\nprice = 1.5\n')
        result = TfvarsHandler.parse_tfvars(str(tfvars))
        assert result["debug"] is False
        assert result["replicas"] == 3
        assert result["price"] == 1.5


class TestTfvarsHandlerWrite:
    """Tests for TfvarsHandler.write_tfvars()."""

    def test_write_simple_values(self, tmp_path):
        out = tmp_path / "out.tfvars"
        TfvarsHandler.write_tfvars(str(out), {
            "region": "us-west-2",
            "project": "demo",
        })
        content = out.read_text()
        assert 'project = "demo"' in content
        assert 'region = "us-west-2"' in content

    def test_write_excludes_sensitive(self, tmp_path):
        out = tmp_path / "out.tfvars"
        TfvarsHandler.write_tfvars(
            str(out),
            {"region": "us-east-1", "secret_key": "hunter2"},
            sensitive_names={"secret_key"},
        )
        content = out.read_text()
        assert "region" in content
        assert "secret_key" not in content
        assert "hunter2" not in content

    def test_write_formats_bools_and_numbers(self, tmp_path):
        out = tmp_path / "out.tfvars"
        TfvarsHandler.write_tfvars(str(out), {
            "enabled": True,
            "disabled": False,
            "count": 5,
        })
        content = out.read_text()
        assert "count = 5" in content
        assert "disabled = false" in content
        assert "enabled = true" in content


# ---------------------------------------------------------------------------
# SettingsDialog tests
# ---------------------------------------------------------------------------

class TestSettingsDialog:
    """Tests for SettingsDialog."""

    @needs_qt
    def test_loads_current_values(self, qtbot, tmp_path):
        from terrygui.config import Settings
        from terrygui.ui.dialogs.settings_dialog import SettingsDialog

        settings = Settings()
        settings.set("editor_command", "vim")
        settings.set("terraform_binary", "/usr/local/bin/terraform")
        settings.set("confirmations.apply", False)

        dialog = SettingsDialog(settings)
        qtbot.addWidget(dialog)

        assert dialog.editor_edit.text() == "vim"
        assert dialog.terraform_edit.text() == "/usr/local/bin/terraform"
        assert dialog.confirm_apply.isChecked() is False

    @needs_qt
    def test_save_persists_changes(self, qtbot, tmp_path):
        from terrygui.config import Settings
        from terrygui.ui.dialogs.settings_dialog import SettingsDialog

        settings = Settings()
        settings.config_file = tmp_path / "settings.json"

        dialog = SettingsDialog(settings)
        qtbot.addWidget(dialog)

        dialog.editor_edit.setText("nvim")
        dialog.terraform_edit.setText("/opt/terraform")
        dialog.confirm_apply.setChecked(False)
        dialog._on_save()

        assert settings.get("editor_command") == "nvim"
        assert settings.get("terraform_binary") == "/opt/terraform"
        assert settings.get("confirmations.apply") is False

    @needs_qt
    def test_cancel_does_not_persist(self, qtbot):
        from terrygui.config import Settings
        from terrygui.ui.dialogs.settings_dialog import SettingsDialog

        settings = Settings()
        original_editor = settings.get("editor_command", "code")

        dialog = SettingsDialog(settings)
        qtbot.addWidget(dialog)

        dialog.editor_edit.setText("emacs")
        dialog.reject()

        assert settings.get("editor_command", "code") == original_editor

    @needs_qt
    def test_empty_editor_defaults_to_code(self, qtbot, tmp_path):
        from terrygui.config import Settings
        from terrygui.ui.dialogs.settings_dialog import SettingsDialog

        settings = Settings()
        settings.config_file = tmp_path / "settings.json"

        dialog = SettingsDialog(settings)
        qtbot.addWidget(dialog)

        dialog.editor_edit.setText("")
        dialog._on_save()

        assert settings.get("editor_command") == "code"


# ---------------------------------------------------------------------------
# Recent Projects tests
# ---------------------------------------------------------------------------

class TestRecentProjects:
    """Tests for recent projects menu behavior."""

    @needs_qt
    def test_empty_menu_shows_placeholder(self, qtbot):
        from terrygui.ui.main_window import MainWindow

        with patch("terrygui.ui.main_window.validate_terraform_installed", return_value=(True, "1.0")):
            window = MainWindow()
            qtbot.addWidget(window)

        window.settings.set("recent_projects", [])
        window._rebuild_recent_menu()

        actions = window._recent_menu.actions()
        assert len(actions) == 1
        assert not actions[0].isEnabled()
        assert "No recent" in actions[0].text()

    @needs_qt
    def test_populated_menu_has_items(self, qtbot, tmp_path):
        from terrygui.ui.main_window import MainWindow

        with patch("terrygui.ui.main_window.validate_terraform_installed", return_value=(True, "1.0")):
            window = MainWindow()
            qtbot.addWidget(window)

        paths = [str(tmp_path / "proj1"), str(tmp_path / "proj2")]
        window.settings.set("recent_projects", paths)
        window._rebuild_recent_menu()

        actions = window._recent_menu.actions()
        # 2 project items + separator + clear action = 4
        assert len(actions) == 4
        assert actions[0].text() == paths[0]
        assert actions[1].text() == paths[1]

    @needs_qt
    def test_clear_empties_list(self, qtbot):
        from terrygui.ui.main_window import MainWindow

        with patch("terrygui.ui.main_window.validate_terraform_installed", return_value=(True, "1.0")):
            window = MainWindow()
            qtbot.addWidget(window)

        window.settings.set("recent_projects", ["/some/path"])
        window._clear_recent_projects()

        assert window.settings.get_recent_projects() == []


# ---------------------------------------------------------------------------
# Keyboard shortcut tests
# ---------------------------------------------------------------------------

class TestKeyboardShortcuts:
    """Tests for button keyboard shortcuts."""

    @needs_qt
    def test_init_button_shortcut(self, qtbot):
        from terrygui.ui.main_window import MainWindow

        with patch("terrygui.ui.main_window.validate_terraform_installed", return_value=(True, "1.0")):
            window = MainWindow()
            qtbot.addWidget(window)

        assert window.init_button.shortcut().toString() == "Ctrl+I"

    @needs_qt
    def test_plan_button_shortcut(self, qtbot):
        from terrygui.ui.main_window import MainWindow

        with patch("terrygui.ui.main_window.validate_terraform_installed", return_value=(True, "1.0")):
            window = MainWindow()
            qtbot.addWidget(window)

        assert window.plan_button.shortcut().toString() == "Ctrl+P"

    @needs_qt
    def test_apply_button_shortcut(self, qtbot):
        from terrygui.ui.main_window import MainWindow

        with patch("terrygui.ui.main_window.validate_terraform_installed", return_value=(True, "1.0")):
            window = MainWindow()
            qtbot.addWidget(window)

        assert window.apply_button.shortcut().toString() == "Ctrl+Shift+A"


# ---------------------------------------------------------------------------
# Import / Export integration tests
# ---------------------------------------------------------------------------

class TestImportExport:
    """Integration tests for .tfvars import/export via VariablesPanel."""

    @needs_qt
    def test_import_populates_matching_variables(self, qtbot, tmp_path):
        from terrygui.ui.widgets.variable_input import VariablesPanel

        panel = VariablesPanel()
        qtbot.addWidget(panel)

        variables = [
            TerraformVariable(name="region", type="string"),
            TerraformVariable(name="count", type="number"),
            TerraformVariable(name="extra", type="string"),
        ]
        panel.load_variables(variables)

        # Write a .tfvars with partial matches
        tfvars = tmp_path / "import.tfvars"
        tfvars.write_text('region = "eu-west-1"\ncount = 10\n')

        values = TfvarsHandler.parse_tfvars(str(tfvars))
        count = panel.set_values(values)

        assert count == 2
        assert panel.get_all_values()["region"] == "eu-west-1"
        assert panel.get_all_values()["count"] == "10"  # set via setText, comes back as string

    @needs_qt
    def test_export_excludes_sensitive(self, qtbot, tmp_path):
        from terrygui.ui.widgets.variable_input import VariablesPanel

        panel = VariablesPanel()
        qtbot.addWidget(panel)

        variables = [
            TerraformVariable(name="region", type="string", default="us-east-1"),
            TerraformVariable(name="api_key", type="string", sensitive=True),
        ]
        panel.load_variables(variables)

        out = tmp_path / "export.tfvars"
        values = panel.get_non_sensitive_values()
        sensitive = panel.get_sensitive_names()
        TfvarsHandler.write_tfvars(str(out), values, sensitive)

        content = out.read_text()
        assert "region" in content
        assert "api_key" not in content
