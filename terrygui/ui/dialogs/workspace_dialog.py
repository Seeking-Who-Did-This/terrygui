"""
Workspace creation and deletion dialogs for TerryGUI.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton,
)
from PySide6.QtCore import Qt

from ...security.sanitizer import InputSanitizer, SecurityError


class WorkspaceDialog(QDialog):
    """
    Dialog for creating or deleting a workspace.

    Mode "create": text input with validation.
    Mode "delete": confirmation with workspace name displayed.
    """

    def __init__(self, mode: str, workspace_name_value: str = "",
                 parent=None):
        """
        Args:
            mode: "create" or "delete"
            workspace_name_value: For delete mode, the name to confirm.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._mode = mode
        self._workspace_name_value = workspace_name_value
        self._init_ui()

    def _init_ui(self):
        if self._mode == "create":
            self._init_create_ui()
        else:
            self._init_delete_ui()

    def _init_create_ui(self):
        self.setWindowTitle("New Workspace")
        self.setMinimumWidth(350)
        self.setModal(True)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Enter a name for the new workspace:"))

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("workspace-name")
        self._name_input.textChanged.connect(self._on_name_changed)
        layout.addWidget(self._name_input)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: red; font-size: 11px;")
        layout.addWidget(self._error_label)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self._create_button = QPushButton("Create")
        self._create_button.setEnabled(False)
        self._create_button.clicked.connect(self.accept)
        button_layout.addWidget(self._create_button)

        layout.addLayout(button_layout)

    def _init_delete_ui(self):
        self.setWindowTitle("Delete Workspace")
        self.setMinimumWidth(350)
        self.setModal(True)

        layout = QVBoxLayout(self)

        warning = QLabel(
            f"Are you sure you want to delete workspace "
            f"<b>{self._workspace_name_value}</b>?"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        note = QLabel(
            "This will remove the workspace. Any resources in this "
            "workspace's state may become orphaned."
        )
        note.setStyleSheet("color: gray; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addSpacing(12)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet(
            "QPushButton { color: white; background-color: #cc0000; "
            "font-weight: bold; padding: 6px 16px; }"
        )
        delete_btn.clicked.connect(self.accept)
        button_layout.addWidget(delete_btn)

        layout.addLayout(button_layout)

    def _on_name_changed(self, text: str):
        """Validate workspace name as user types."""
        if not text:
            self._create_button.setEnabled(False)
            self._error_label.setText("")
            return

        try:
            InputSanitizer.sanitize_workspace_name(text)
            self._create_button.setEnabled(True)
            self._error_label.setText("")
        except SecurityError as e:
            self._create_button.setEnabled(False)
            self._error_label.setText(str(e))

    def workspace_name(self) -> str:
        """Return the workspace name (for create mode)."""
        if self._mode == "create":
            return self._name_input.text().strip()
        return self._workspace_name_value
