"""
Confirmation dialog for destructive Terraform operations.

Implements a checkbox-gated confirmation pattern to prevent
accidental apply/destroy actions.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QPushButton, QFrame,
)
from PySide6.QtCore import Qt


class ConfirmDialog(QDialog):
    """
    Confirmation dialog for apply/destroy operations.

    The action button is disabled until the user checks the
    acknowledgment checkbox. Styling differs by operation:
    - apply: green "Continue" button
    - destroy: bold red "Destroy" button
    """

    def __init__(
        self,
        operation: str,
        details: Optional[dict] = None,
        parent=None,
    ):
        """
        Args:
            operation: "apply" or "destroy"
            details: Optional dict with keys like 'workspace',
                     'to_add', 'to_change', 'to_destroy'
            parent: Parent widget
        """
        super().__init__(parent)
        self.operation = operation.lower()
        self.details = details or {}
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle(f"Confirm Terraform {self.operation.title()}")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # --- Header ---
        header = QLabel(f"Confirm Terraform {self.operation.title()}")
        header.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider)

        # --- Details ---
        workspace = self.details.get("workspace", "default")
        if self.operation == "destroy":
            desc = (
                f"This will <b>destroy</b> infrastructure in "
                f"workspace: <b>{workspace}</b>"
            )
        else:
            desc = (
                f"This will modify infrastructure in "
                f"workspace: <b>{workspace}</b>"
            )
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Resource counts (if available)
        to_add = self.details.get("to_add")
        to_change = self.details.get("to_change")
        to_destroy = self.details.get("to_destroy")
        if any(v is not None for v in (to_add, to_change, to_destroy)):
            counts_text = ""
            if to_add is not None:
                counts_text += f"Resources to add: {to_add}\n"
            if to_change is not None:
                counts_text += f"Resources to change: {to_change}\n"
            if to_destroy is not None:
                counts_text += f"Resources to destroy: {to_destroy}\n"
            counts_label = QLabel(counts_text.strip())
            counts_label.setStyleSheet("padding: 8px; font-family: monospace;")
            layout.addWidget(counts_label)

        layout.addSpacing(8)

        # --- Acknowledgment checkbox ---
        if self.operation == "destroy":
            ack_text = (
                "I understand this action will destroy infrastructure "
                "and cannot be undone"
            )
        else:
            ack_text = (
                "I understand this action will modify infrastructure "
                "and may incur costs"
            )
        self._ack_checkbox = QCheckBox(ack_text)
        self._ack_checkbox.stateChanged.connect(self._on_ack_changed)
        layout.addWidget(self._ack_checkbox)

        layout.addSpacing(12)

        # --- Buttons ---
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_button)

        if self.operation == "destroy":
            self._action_button = QPushButton("Destroy")
            self._action_button_enabled_style = (
                "QPushButton { color: white; background-color: #cc0000; "
                "font-weight: bold; padding: 6px 16px; }"
            )
        else:
            self._action_button = QPushButton("Continue")
            self._action_button_enabled_style = (
                "QPushButton { color: white; background-color: #22882a; "
                "padding: 6px 16px; }"
            )

        self._action_button.setEnabled(False)
        self._action_button.clicked.connect(self.accept)
        button_layout.addWidget(self._action_button)

        layout.addLayout(button_layout)

    def _on_ack_changed(self, state: int):
        """Enable/disable action button based on checkbox."""
        checked = state == Qt.CheckState.Checked.value
        self._action_button.setEnabled(checked)
        if checked:
            self._action_button.setStyleSheet(self._action_button_enabled_style)
        else:
            self._action_button.setStyleSheet("")
