"""
Main application window for TerryGUI.

MainWindow is a thin tab host.  Per-project logic lives in ProjectPane.
"""

import os
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QLabel, QPushButton,
    QStatusBar, QMessageBox, QFileDialog,
    QTabWidget, QTabBar, QStackedWidget, QInputDialog,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction

from ..config import Settings
from ..utils import validate_terraform_installed

from .widgets.project_pane import ProjectPane

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom tab bar: natural-width tabs with scroll-arrow support
# ---------------------------------------------------------------------------

class _AppTabBar(QTabBar):
    """QTabBar with natural-width tabs (not stretched) and scroll arrows."""

    # Pixels to pull the close button away from the tab's right edge.
    CLOSE_BTN_INSET = 5

    tab_double_clicked = Signal(int)  # emits tab index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUsesScrollButtons(True)
        # Don't stretch tabs to fill bar width.
        self.setExpanding(False)
        # Comfortable horizontal breathing room; rounded corners.
        self.setStyleSheet(
            "QTabBar::tab { padding: 6px 8px 6px 8px; border-radius: 4px;"
            " border: 1px solid palette(mid); }"
            "QTabBar::tab:selected { border-color: palette(highlight); }"
        )

    # ------------------------------------------------------------------
    # Close-button repositioning
    # ------------------------------------------------------------------

    def _reposition_close_buttons(self):
        """Place each close button CLOSE_BTN_INSET px from the tab's right edge.

        Position is computed from tabRect() (absolute), NOT by shifting the
        button's current geometry.  This makes the call idempotent: repeated
        calls always produce the same result regardless of prior button state.

        If tabRect(i).right() is still <= 0 the window hasn't been laid out
        with real dimensions yet — reschedule and retry.
        """
        for i in range(self.count()):
            tab_r = self.tabRect(i)
            if tab_r.right() <= 0:
                QTimer.singleShot(10, self._reposition_close_buttons)
                return
            btn = self.tabButton(i, QTabBar.ButtonPosition.RightSide)
            if btn:
                bw, bh = btn.width(), btn.height()
                x = tab_r.right() - bw - self.CLOSE_BTN_INSET
                y = tab_r.center().y() - bh // 2
                btn.setGeometry(x, y, bw, bh)

    def _schedule_reposition(self):
        """Defer repositioning to after Qt finishes its own layout pass."""
        QTimer.singleShot(0, self._reposition_close_buttons)

    def tabLayoutChange(self):
        super().tabLayoutChange()
        self._schedule_reposition()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_reposition()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_reposition()

    def mouseDoubleClickEvent(self, event):
        idx = self.tabAt(event.position().toPoint())
        if idx >= 0:
            self.tab_double_clicked.emit(idx)
        else:
            super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    """Main application window — hosts per-project tabs."""

    def __init__(self):
        super().__init__()

        self.settings = Settings()

        self._init_ui()
        self._check_terraform_installed()
        self._restore_session_tabs()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setWindowTitle("TerryGUI - Terraform Manager")

        width = self.settings.get("window.width", 900)
        height = self.settings.get("window.height", 700)
        self.resize(width, height)

        self._create_menu_bar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Stack: index 0 = landing page, index 1 = tab widget
        self._stack = QStackedWidget()
        main_layout.addWidget(self._stack)

        self._landing_page = self._create_landing_page()
        self._stack.addWidget(self._landing_page)   # index 0

        self._tab_bar = _AppTabBar()
        self._tab_bar.tab_double_clicked.connect(self._on_tab_double_clicked)

        self._tab_widget = QTabWidget()
        self._tab_widget.setTabBar(self._tab_bar)
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        self._stack.addWidget(self._tab_widget)     # index 1

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _create_landing_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel("Open a Terraform project to begin")
        label.setStyleSheet("color: gray; font-size: 14px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        open_btn = QPushButton("Open Project...")
        open_btn.clicked.connect(self._on_browse_project)

        layout.addWidget(label)
        layout.addWidget(open_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return widget

    def _create_menu_bar(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        browse_action = QAction("&Open Terraform Project...", self)
        browse_action.setShortcut("Ctrl+O")
        browse_action.triggered.connect(self._on_browse_project)
        file_menu.addAction(browse_action)

        edit_action = QAction("&Edit project in editor", self)
        edit_action.setShortcut("Ctrl+E")
        edit_action.triggered.connect(
            lambda: self._active_pane() and self._active_pane()._on_edit_project()
        )
        file_menu.addAction(edit_action)

        file_menu.addSeparator()

        import_action = QAction("&Import .tfvars...", self)
        import_action.triggered.connect(
            lambda: self._active_pane() and self._active_pane()._on_import_tfvars()
        )
        file_menu.addAction(import_action)

        export_action = QAction("&Export .tfvars...", self)
        export_action.triggered.connect(
            lambda: self._active_pane() and self._active_pane()._on_export_tfvars()
        )
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        self._recent_menu = file_menu.addMenu("Recent Projects")
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_menu)

        file_menu.addSeparator()

        prefs_action = QAction("Edit &Preferences...", self)
        prefs_action.setShortcut("Ctrl+,")
        prefs_action.triggered.connect(self._on_preferences)
        file_menu.addAction(prefs_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        self._view_menu = menubar.addMenu("&View")

        self._state_action = QAction("&State Resources", self)
        self._state_action.setShortcut("Ctrl+Shift+S")
        self._state_action.triggered.connect(
            lambda: self._delegate_to_pane("_show_state_viewer")
        )
        self._view_menu.addAction(self._state_action)

        self._outputs_action = QAction("&Outputs", self)
        self._outputs_action.setShortcut("Ctrl+Shift+O")
        self._outputs_action.triggered.connect(
            lambda: self._delegate_to_pane("_show_outputs_viewer")
        )
        self._view_menu.addAction(self._outputs_action)

        self._view_menu.addSeparator()

        refresh_action = QAction("&Refresh Project", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(
            lambda: self._delegate_to_pane("_on_refresh_project")
        )
        self._view_menu.addAction(refresh_action)

        # Workspace menu
        workspace_menu = menubar.addMenu("&Workspace")

        new_ws_action = QAction("&New workspace in project...", self)
        new_ws_action.triggered.connect(
            lambda: self._delegate_to_pane("_on_new_workspace")
        )
        workspace_menu.addAction(new_ws_action)

        delete_ws_action = QAction("&Delete workspace in project...", self)
        delete_ws_action.triggered.connect(
            lambda: self._delegate_to_pane("_on_delete_workspace")
        )
        workspace_menu.addAction(delete_ws_action)

        workspace_menu.addSeparator()

        refresh_ws_action = QAction("&Refresh List", self)
        refresh_ws_action.triggered.connect(
            lambda: self._delegate_to_pane("_refresh_workspace_info")
        )
        workspace_menu.addAction(refresh_ws_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    def _active_pane(self) -> Optional[ProjectPane]:
        widget = self._tab_widget.currentWidget()
        return widget if isinstance(widget, ProjectPane) else None

    def _delegate_to_pane(self, method_name: str):
        pane = self._active_pane()
        if pane:
            getattr(pane, method_name)()

    def _new_tab(self, project_path: Optional[str] = None):
        pane = ProjectPane(self.settings, parent=self)
        pane.status_message.connect(self._on_pane_status_message)
        pane.tab_title_changed.connect(
            lambda title, p=pane: self._on_tab_title_changed(p, title)
        )

        label = os.path.basename(project_path) if project_path else "New Tab"
        idx = self._tab_widget.addTab(pane, label)
        if project_path:
            self._tab_widget.setTabToolTip(idx, project_path)
        self._tab_widget.setCurrentIndex(idx)
        self._stack.setCurrentIndex(1)

        if project_path:
            try:
                pane.load_project(project_path)
            except Exception as e:
                QMessageBox.critical(self, "Error Loading Project", str(e))

    def _open_project_in_tab(self, path: str):
        """Open project in a tab; focus existing tab if already open."""
        for i in range(self._tab_widget.count()):
            pane = self._tab_widget.widget(i)
            if isinstance(pane, ProjectPane) and pane.current_project_path == path:
                self._tab_widget.setCurrentIndex(i)
                return
        self._new_tab(project_path=path)

    def _on_tab_changed(self, index: int):
        pane = self._tab_widget.widget(index)
        if isinstance(pane, ProjectPane) and pane.current_project_path:
            self.setWindowTitle(f"{pane.get_tab_title()} — TerryGUI")
            if not pane.is_operation_running():
                self.status_bar.showMessage(pane.get_status_text())
        else:
            self.setWindowTitle("TerryGUI - Terraform Manager")

    def _on_tab_close_requested(self, index: int):
        pane = self._tab_widget.widget(index)
        if isinstance(pane, ProjectPane) and pane.is_operation_running():
            answer = QMessageBox.question(
                self,
                "Operation Running",
                "A Terraform operation is running in this tab. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        if isinstance(pane, ProjectPane):
            pane.save_state()

        self._tab_widget.removeTab(index)

        if self._tab_widget.count() == 0:
            self._stack.setCurrentIndex(0)
            self.setWindowTitle("TerryGUI - Terraform Manager")

    def _on_pane_status_message(self, msg: str):
        sender_pane = self.sender()
        if sender_pane is self._active_pane():
            self.status_bar.showMessage(msg)

    def _on_tab_title_changed(self, pane: ProjectPane, title: str):
        for i in range(self._tab_widget.count()):
            if self._tab_widget.widget(i) is pane:
                self._tab_widget.setTabText(i, title)
                if self._tab_widget.currentWidget() is pane:
                    self.setWindowTitle(f"{title} — TerryGUI")
                break

    # ------------------------------------------------------------------
    # Browse / open project
    # ------------------------------------------------------------------

    def _on_tab_double_clicked(self, index: int):
        """Prompt the user to set or clear the nickname for the double-clicked tab."""
        pane = self._tab_widget.widget(index)
        if not isinstance(pane, ProjectPane) or not pane.current_project_path:
            return

        folder = os.path.basename(pane.current_project_path)
        current_nick = pane.project_manager.get_nickname() if pane.project_manager else ""

        nick, ok = QInputDialog.getText(
            self,
            "Rename Tab",
            f'Nickname for "{folder}":\n(leave blank to use folder name)',
            text=current_nick,
        )
        if ok:
            pane.set_nickname(nick)

    def _on_browse_project(self):
        project_path = QFileDialog.getExistingDirectory(
            self,
            "Select Terraform Project Directory",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not project_path:
            return
        self._open_project_in_tab(project_path)

    # ------------------------------------------------------------------
    # Session restoration
    # ------------------------------------------------------------------

    def _restore_session_tabs(self):
        open_projects = self.settings.get_open_projects()
        for path in open_projects:
            if os.path.exists(path):
                try:
                    self._new_tab(project_path=path)
                except Exception as e:
                    logger.warning(f"Failed to restore tab for {path}: {e}")

        # Fall back to last project if no session tabs were saved
        if self._tab_widget.count() == 0:
            last = self.settings.get_last_project()
            if last and os.path.exists(last):
                try:
                    self._new_tab(project_path=last)
                except Exception as e:
                    logger.warning(f"Failed to restore last project {last}: {e}")

    # ------------------------------------------------------------------
    # Terraform installed check
    # ------------------------------------------------------------------

    def _check_terraform_installed(self):
        terraform_binary = self.settings.get("terraform_binary", "terraform")
        is_installed, version = validate_terraform_installed(terraform_binary)

        if not is_installed:
            logger.warning("Terraform not found in PATH")
            self.status_bar.showMessage(
                "Terraform not found. Install or configure path in Settings."
            )
        else:
            logger.info(f"Terraform found: {version}")

    # ------------------------------------------------------------------
    # Recent projects
    # ------------------------------------------------------------------

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        recent = self.settings.get_recent_projects()

        if not recent:
            placeholder = QAction("(No recent projects)", self)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)
            return

        for path in recent:
            action = QAction(path, self)
            action.triggered.connect(lambda checked, p=path: self._open_project_in_tab(p))
            self._recent_menu.addAction(action)

        self._recent_menu.addSeparator()
        clear_action = QAction("Clear Recent Projects", self)
        clear_action.triggered.connect(self._clear_recent_projects)
        self._recent_menu.addAction(clear_action)

    def _clear_recent_projects(self):
        self.settings.set("recent_projects", [])
        self.settings.save()

    # ------------------------------------------------------------------
    # Preferences / About
    # ------------------------------------------------------------------

    def _on_preferences(self):
        from .dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.settings, parent=self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self._check_terraform_installed()

    def _show_about(self):
        from .. import __version__
        QMessageBox.about(
            self,
            "About TerryGUI",
            f"<h2>TerryGUI v{__version__}</h2>"
            "<p>A professional Qt-based GUI for managing Terraform projects.</p>"
            "<p>Copyright 2026 TerryGUI Contributors</p>"
            "<p>Licensed under MIT License</p>",
        )

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self.settings.set("window.width", self.width())
        self.settings.set("window.height", self.height())
        self.settings.set("window.maximized", self.isMaximized())

        open_paths = []
        for i in range(self._tab_widget.count()):
            pane = self._tab_widget.widget(i)
            if isinstance(pane, ProjectPane):
                pane.save_state()
                if pane.current_project_path:
                    open_paths.append(pane.current_project_path)

        self.settings.set_open_projects(open_paths)
        self.settings.save()

        logger.info("Application closing")
        event.accept()
