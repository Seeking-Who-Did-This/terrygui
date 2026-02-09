"""
State viewer widget for inspecting Terraform state.

Provides a split-panel view: resource list on the left,
resource details on the right, with a toggle between
Resources and Outputs views.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QTextEdit, QPushButton, QLabel,
    QButtonGroup,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...core.state_manager import StateManager

logger = logging.getLogger(__name__)


class StateViewerWidget(QWidget):
    """
    Widget for viewing Terraform state resources and outputs.

    Layout:
    - Top bar: resource count label + Refresh button
    - Middle: splitter with resource list (left) and detail view (right)
    - Bottom: Resources / Outputs toggle buttons
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._manager: Optional[StateManager] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # --- Top bar ---
        top_bar = QHBoxLayout()
        self._count_label = QLabel("State Resources")
        top_bar.addWidget(self._count_label)
        top_bar.addStretch()

        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.clicked.connect(self._on_refresh)
        top_bar.addWidget(self._refresh_button)
        layout.addLayout(top_bar)

        # --- Splitter: resource list + detail view ---
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        self._resource_list = QListWidget()
        self._resource_list.currentRowChanged.connect(self._on_resource_selected)
        self._splitter.addWidget(self._resource_list)

        self._detail_view = QTextEdit()
        self._detail_view.setReadOnly(True)
        self._detail_view.setFont(QFont("Consolas", 9))
        self._splitter.addWidget(self._detail_view)

        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 2)

        layout.addWidget(self._splitter, stretch=1)

        # --- Bottom toggle: Resources / Outputs ---
        toggle_layout = QHBoxLayout()

        self._resources_button = QPushButton("Resources")
        self._resources_button.setCheckable(True)
        self._resources_button.setChecked(True)

        self._outputs_button = QPushButton("Outputs")
        self._outputs_button.setCheckable(True)

        self._toggle_group = QButtonGroup(self)
        self._toggle_group.setExclusive(True)
        self._toggle_group.addButton(self._resources_button, 0)
        self._toggle_group.addButton(self._outputs_button, 1)
        self._toggle_group.idClicked.connect(self._on_view_toggled)

        toggle_layout.addWidget(self._resources_button)
        toggle_layout.addWidget(self._outputs_button)
        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)

    def set_manager(self, manager: StateManager) -> None:
        """Set the StateManager and load initial data."""
        self._manager = manager
        self._load_resources()

    def _on_refresh(self):
        """Refresh the current view."""
        if self._resources_button.isChecked():
            self._load_resources()
        else:
            self._load_outputs()

    def _load_resources(self):
        """Fetch and display the resource list."""
        self._resource_list.clear()
        self._detail_view.clear()

        if not self._manager:
            self._count_label.setText("State Resources")
            return

        resources = self._manager.list_resources()
        self._count_label.setText(f"State Resources ({len(resources)})")

        for res in resources:
            self._resource_list.addItem(res.address)

    def _load_outputs(self):
        """Fetch and display terraform outputs."""
        self._detail_view.clear()

        if not self._manager:
            return

        output = self._manager.get_outputs()
        self._detail_view.setPlainText(output)

    def _on_resource_selected(self, row: int):
        """Load details for the selected resource."""
        if row < 0 or not self._manager:
            self._detail_view.clear()
            return

        item = self._resource_list.item(row)
        if item is None:
            return

        address = item.text()
        details = self._manager.get_resource_details(address)
        self._detail_view.setPlainText(details)

    def _on_view_toggled(self, button_id: int):
        """Switch between Resources and Outputs view."""
        if button_id == 0:
            # Resources view: show list + details
            self._resource_list.setVisible(True)
            self._load_resources()
        else:
            # Outputs view: hide list, show outputs in detail pane
            self._resource_list.setVisible(False)
            self._load_outputs()
