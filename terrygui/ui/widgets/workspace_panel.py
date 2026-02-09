"""
Workspace selector panel for TerryGUI.

Provides a dropdown to switch workspaces and buttons to create/delete.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton,
)
from PySide6.QtCore import Signal

from ...core.workspace_manager import WorkspaceManager, WorkspaceInfo

logger = logging.getLogger(__name__)


class WorkspacePanelWidget(QWidget):
    """
    Workspace selector with New / Delete buttons.

    Layout: Workspace: [dropdown ▼]  [New] [Delete]

    Emits workspace_changed(str) when the user selects a different workspace.
    """

    workspace_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._manager: Optional[WorkspaceManager] = None
        self._refreshing = False  # guard against signal loops
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Workspace:"))

        self._combo = QComboBox()
        self._combo.setMinimumWidth(160)
        self._combo.currentTextChanged.connect(self._on_selection_changed)
        layout.addWidget(self._combo)

        self._new_button = QPushButton("New")
        self._new_button.setToolTip("Create a new workspace")
        self._new_button.clicked.connect(self._on_new_clicked)
        layout.addWidget(self._new_button)

        self._delete_button = QPushButton("Delete")
        self._delete_button.setToolTip("Delete the selected workspace")
        self._delete_button.clicked.connect(self._on_delete_clicked)
        layout.addWidget(self._delete_button)

        layout.addStretch()
        self.setEnabled(False)

    def set_manager(self, manager: WorkspaceManager):
        """Set the workspace manager and refresh the list."""
        self._manager = manager
        self.setEnabled(True)
        self.refresh()

    def refresh(self):
        """Reload the workspace list from terraform."""
        if self._manager is None:
            return

        self._refreshing = True
        try:
            workspaces = self._manager.list_workspaces()
            self._combo.clear()
            current_index = 0
            for i, ws in enumerate(workspaces):
                self._combo.addItem(ws.name)
                if ws.is_current:
                    current_index = i
            self._combo.setCurrentIndex(current_index)

            # Can't delete the "default" workspace or current workspace
            self._update_delete_enabled()
        finally:
            self._refreshing = False

    def current_workspace(self) -> str:
        """Return the currently selected workspace name."""
        return self._combo.currentText() or "default"

    def _update_delete_enabled(self):
        """Disable delete for 'default' workspace."""
        name = self._combo.currentText()
        self._delete_button.setEnabled(name != "default" and name != "")

    def _on_selection_changed(self, name: str):
        """Handle workspace dropdown selection change."""
        if self._refreshing or not name or self._manager is None:
            return

        success = self._manager.switch_workspace(name)
        if success:
            logger.info(f"Switched to workspace: {name}")
            self._update_delete_enabled()
            self.workspace_changed.emit(name)
        else:
            # Switch failed — refresh to restore actual state
            self.refresh()

    def _on_new_clicked(self):
        """Open dialog to create a new workspace."""
        from ..dialogs.workspace_dialog import WorkspaceDialog

        dialog = WorkspaceDialog("create", parent=self)
        if dialog.exec() == WorkspaceDialog.DialogCode.Accepted:
            name = dialog.workspace_name()
            if name and self._manager is not None:
                success = self._manager.create_workspace(name)
                if success:
                    self.refresh()
                    self.workspace_changed.emit(name)

    def _on_delete_clicked(self):
        """Open dialog to confirm workspace deletion."""
        from ..dialogs.workspace_dialog import WorkspaceDialog

        name = self._combo.currentText()
        if not name or name == "default":
            return

        dialog = WorkspaceDialog("delete", workspace_name_value=name, parent=self)
        if dialog.exec() == WorkspaceDialog.DialogCode.Accepted:
            if self._manager is not None:
                # Switch to default first, then delete
                self._manager.switch_workspace("default")
                success = self._manager.delete_workspace(name)
                if success:
                    self.refresh()
                    self.workspace_changed.emit("default")
