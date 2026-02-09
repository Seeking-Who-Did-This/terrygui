"""
Settings dialog for TerryGUI.

Allows users to configure editor command, terraform binary,
and confirmation dialog preferences.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QCheckBox, QPushButton, QGroupBox,
    QWidget,
)

from ...config import Settings


class SettingsDialog(QDialog):
    """Settings preferences dialog."""

    def __init__(self, settings: Settings, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.settings = settings
        self._init_ui()
        self._load_values()

    def _init_ui(self):
        """Build the dialog UI."""
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # General settings
        general_group = QGroupBox("General")
        general_form = QFormLayout()

        self.editor_edit = QLineEdit()
        self.editor_edit.setPlaceholderText("code")
        general_form.addRow("Editor command:", self.editor_edit)

        self.terraform_edit = QLineEdit()
        self.terraform_edit.setPlaceholderText("terraform")
        general_form.addRow("Terraform binary:", self.terraform_edit)

        general_group.setLayout(general_form)
        layout.addWidget(general_group)

        # Confirmation settings
        confirm_group = QGroupBox("Confirmations")
        confirm_layout = QVBoxLayout()

        self.confirm_apply = QCheckBox("Confirm before apply")
        confirm_layout.addWidget(self.confirm_apply)

        self.confirm_destroy = QCheckBox("Confirm before destroy")
        confirm_layout.addWidget(self.confirm_destroy)

        self.confirm_ws_delete = QCheckBox("Confirm before workspace delete")
        confirm_layout.addWidget(self.confirm_ws_delete)

        confirm_group.setLayout(confirm_layout)
        layout.addWidget(confirm_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def _load_values(self):
        """Load current settings into form fields."""
        self.editor_edit.setText(self.settings.get("editor_command", "code"))
        self.terraform_edit.setText(self.settings.get("terraform_binary", "terraform"))
        self.confirm_apply.setChecked(self.settings.get("confirmations.apply", True))
        self.confirm_destroy.setChecked(self.settings.get("confirmations.destroy", True))
        self.confirm_ws_delete.setChecked(self.settings.get("confirmations.workspace_delete", True))

    def _on_save(self):
        """Save form values to settings."""
        editor = self.editor_edit.text().strip() or "code"
        terraform = self.terraform_edit.text().strip() or "terraform"

        self.settings.set("editor_command", editor)
        self.settings.set("terraform_binary", terraform)
        self.settings.set("confirmations.apply", self.confirm_apply.isChecked())
        self.settings.set("confirmations.destroy", self.confirm_destroy.isChecked())
        self.settings.set("confirmations.workspace_delete", self.confirm_ws_delete.isChecked())
        self.settings.save()
        self.accept()
