"""
Main application window for TerryGUI.

This is the primary UI window containing all major components:
project selector, variable inputs, operation buttons, and output viewer.
"""

import os
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog,
    QStatusBar, QMessageBox, QCheckBox, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QAction

from ..config import Settings
from ..core import TerraformParser, ProjectManager, TerraformRunner, CommandResult, WorkspaceManager, StateManager
from ..core.tfvars_handler import TfvarsHandler
from ..utils import validate_terraform_installed, validators
from ..security import InputSanitizer, SecurityError

from .widgets.variable_input import VariablesPanel
from .widgets.output_viewer import OutputViewerWidget
from .widgets.state_viewer import StateViewerWidget
from .dialogs.confirm_dialog import ConfirmDialog
from .dialogs.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker for running Terraform commands off the UI thread
# ---------------------------------------------------------------------------

class _OperationWorker(QObject):
    """Runs a TerraformRunner operation in a background thread."""

    line_output = Signal(str)
    finished = Signal(object)  # emits CommandResult

    def __init__(self, runner: TerraformRunner, operation: str,
                 variables: Optional[dict] = None,
                 var_types: Optional[dict] = None,
                 auto_approve: bool = False):
        super().__init__()
        self.runner = runner
        self.operation = operation
        self.variables = variables
        self.var_types = var_types
        self.auto_approve = auto_approve

    def run(self):
        """Execute the operation and emit result when done."""
        try:
            if self.operation == "init":
                result = self.runner.init(output_callback=self.line_output.emit)
            elif self.operation == "validate":
                result = self.runner.validate(output_callback=self.line_output.emit)
            elif self.operation == "plan":
                result = self.runner.plan(
                    variables=self.variables or {},
                    var_types=self.var_types or {},
                    output_callback=self.line_output.emit,
                )
            elif self.operation == "apply":
                result = self.runner.apply(
                    variables=self.variables or {},
                    var_types=self.var_types or {},
                    auto_approve=self.auto_approve,
                    output_callback=self.line_output.emit,
                )
            elif self.operation == "destroy":
                result = self.runner.destroy(
                    variables=self.variables or {},
                    var_types=self.var_types or {},
                    auto_approve=self.auto_approve,
                    output_callback=self.line_output.emit,
                )
            else:
                result = CommandResult(
                    exit_code=1, stdout="", stderr=f"Unknown operation: {self.operation}",
                    success=False, command=self.operation,
                )
        except Exception as exc:
            result = CommandResult(
                exit_code=1, stdout="", stderr=str(exc),
                success=False, command=self.operation,
            )
        self.finished.emit(result)


class MainWindow(QMainWindow):
    """Main application window."""

    # Internal signal used to relay output from worker thread to UI thread
    _relay_output = Signal(str)

    def __init__(self):
        super().__init__()

        self.settings = Settings()
        self.current_project_path: Optional[str] = None
        self.project_manager: Optional[ProjectManager] = None
        self.terraform_parser: Optional[TerraformParser] = None
        self.terraform_runner: Optional[TerraformRunner] = None
        self.workspace_manager: Optional[WorkspaceManager] = None
        self.state_manager: Optional[StateManager] = None
        self._state_dialog: Optional["QDialog"] = None

        # Background operation state
        self._worker: Optional[_OperationWorker] = None
        self._worker_thread: Optional[QThread] = None
        self._init_done = False  # tracks whether init has succeeded

        self._init_ui()
        self._update_button_states()
        self._check_terraform_installed()
        self._try_load_last_project()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        """Initialize user interface."""
        self.setWindowTitle("TerryGUI - Terraform Manager")

        width = self.settings.get("window.width", 900)
        height = self.settings.get("window.height", 700)
        self.resize(width, height)

        self._create_menu_bar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Variables panel — scales with window ---
        self.variables_panel = VariablesPanel()
        main_layout.addWidget(self.variables_panel, stretch=1)

        # --- Project info bar (workspace + path), fixed height ---
        self._info_label = QLabel("No project loaded")
        self._info_label.setFixedHeight(28)
        self._info_label.setStyleSheet(
            "color: gray; padding: 2px 8px; background: palette(alternate-base);"
        )
        from PySide6.QtCore import Qt as QtConstants
        self._info_label.setTextFormat(QtConstants.TextFormat.PlainText)
        main_layout.addWidget(self._info_label)

        # Visual divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(divider)

        # --- Output viewer — fixed height with scrollbar ---
        self.output_viewer = OutputViewerWidget()
        self.output_viewer.setMinimumHeight(120)
        self.output_viewer.setMaximumHeight(200)
        main_layout.addWidget(self.output_viewer)

        # --- Operation buttons row ---
        buttons_layout = QHBoxLayout()

        self.init_button = QPushButton("Init")
        self.init_button.setToolTip("Run terraform init (Ctrl+I)")
        self.init_button.setShortcut("Ctrl+I")
        self.init_button.clicked.connect(lambda: self._run_operation("init"))
        buttons_layout.addWidget(self.init_button)

        self.validate_button = QPushButton("Validate")
        self.validate_button.setToolTip("Run terraform validate")
        self.validate_button.clicked.connect(lambda: self._run_operation("validate"))
        buttons_layout.addWidget(self.validate_button)

        self.plan_button = QPushButton("Plan")
        self.plan_button.setToolTip("Run terraform plan (Ctrl+P)")
        self.plan_button.setShortcut("Ctrl+P")
        self.plan_button.clicked.connect(lambda: self._run_operation("plan"))
        buttons_layout.addWidget(self.plan_button)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Run terraform apply (Ctrl+Shift+A)")
        self.apply_button.setShortcut("Ctrl+Shift+A")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        buttons_layout.addWidget(self.apply_button)

        self.destroy_button = QPushButton("Destroy")
        self.destroy_button.setToolTip("Run terraform destroy (with confirmation)")
        self.destroy_button.clicked.connect(self._on_destroy_clicked)
        buttons_layout.addWidget(self.destroy_button)

        buttons_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Cancel running operation")
        self.cancel_button.clicked.connect(self._on_cancel)
        buttons_layout.addWidget(self.cancel_button)

        self.debug_checkbox = QCheckBox("Debug output")
        self.debug_checkbox.setToolTip("Show verbose terraform output")
        buttons_layout.addWidget(self.debug_checkbox)

        main_layout.addLayout(buttons_layout)

        # --- Status bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Internal signal for thread-safe output relay
        self._relay_output.connect(self.output_viewer.append_output)

    def _create_menu_bar(self):
        """Create application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        browse_action = QAction("&Browse project...", self)
        browse_action.setShortcut("Ctrl+O")
        browse_action.triggered.connect(self._on_browse_project)
        file_menu.addAction(browse_action)

        edit_action = QAction("&Edit project in editor", self)
        edit_action.setShortcut("Ctrl+E")
        edit_action.triggered.connect(self._on_edit_project)
        file_menu.addAction(edit_action)

        file_menu.addSeparator()

        import_action = QAction("&Import .tfvars...", self)
        import_action.triggered.connect(self._on_import_tfvars)
        file_menu.addAction(import_action)

        export_action = QAction("&Export .tfvars...", self)
        export_action.triggered.connect(self._on_export_tfvars)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        # Recent Projects submenu
        self._recent_menu = file_menu.addMenu("Recent Projects")
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_menu)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        prefs_action = QAction("&Preferences...", self)
        prefs_action.setShortcut("Ctrl+,")
        prefs_action.triggered.connect(self._on_preferences)
        edit_menu.addAction(prefs_action)

        # View menu
        self._view_menu = menubar.addMenu("&View")

        self._state_action = QAction("&State Resources", self)
        self._state_action.setShortcut("Ctrl+Shift+S")
        self._state_action.triggered.connect(self._show_state_viewer)
        self._view_menu.addAction(self._state_action)

        self._outputs_action = QAction("&Outputs", self)
        self._outputs_action.setShortcut("Ctrl+Shift+O")
        self._outputs_action.triggered.connect(self._show_outputs_viewer)
        self._view_menu.addAction(self._outputs_action)

        self._view_menu.addSeparator()

        refresh_action = QAction("&Refresh Project", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._on_refresh_project)
        self._view_menu.addAction(refresh_action)

        self._view_menu.setEnabled(False)

        # Workspace menu
        workspace_menu = menubar.addMenu("&Workspace")

        new_ws_action = QAction("&New workspace in project...", self)
        new_ws_action.triggered.connect(self._on_new_workspace)
        workspace_menu.addAction(new_ws_action)

        delete_ws_action = QAction("&Delete workspace in project...", self)
        delete_ws_action.triggered.connect(self._on_delete_workspace)
        workspace_menu.addAction(delete_ws_action)

        workspace_menu.addSeparator()

        refresh_ws_action = QAction("&Refresh List", self)
        refresh_ws_action.triggered.connect(self._refresh_workspace_info)
        workspace_menu.addAction(refresh_ws_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ------------------------------------------------------------------
    # Button state machine
    # ------------------------------------------------------------------

    def _update_button_states(self):
        """
        Update operation button enabled/disabled state.

        State machine:
        - No project loaded: all disabled
        - Project loaded, init not run: only Init enabled
        - Init succeeded: Init, Validate, Plan, Apply, Destroy enabled
        - Operation running: all disabled, Cancel enabled
        """
        running = self._worker_thread is not None and self._worker_thread.isRunning()
        has_project = self.current_project_path is not None

        self.init_button.setEnabled(has_project and not running)
        self.validate_button.setEnabled(has_project and self._init_done and not running)
        self.plan_button.setEnabled(has_project and self._init_done and not running)
        self.apply_button.setEnabled(has_project and self._init_done and not running)
        self.destroy_button.setEnabled(has_project and self._init_done and not running)
        self.cancel_button.setEnabled(running)

        # View menu requires init to have completed
        self._view_menu.setEnabled(has_project and self._init_done)

    # ------------------------------------------------------------------
    # Terraform operations
    # ------------------------------------------------------------------

    def _run_operation(self, operation: str):
        """Start a terraform operation in a background thread."""
        if self.terraform_runner is None or self._worker_thread is not None:
            return

        self.output_viewer.clear()
        self.output_viewer.set_label(f"Output — terraform {operation}")
        self.status_bar.showMessage(f"Running terraform {operation}...")

        variables = None
        var_types = None
        auto_approve = False
        if operation in ("plan", "apply", "destroy"):
            if not self.variables_panel.all_valid():
                QMessageBox.warning(
                    self, "Validation Error",
                    "Please fix variable validation errors before running "
                    f"{operation}.",
                )
                return
            variables = self.variables_panel.get_all_values()
            var_types = self.variables_panel.get_var_types()
        if operation in ("apply", "destroy"):
            auto_approve = True  # confirmation was already given via dialog

        worker = _OperationWorker(
            self.terraform_runner, operation,
            variables=variables, var_types=var_types,
            auto_approve=auto_approve,
        )
        thread = QThread()
        worker.moveToThread(thread)

        # Connect signals — ordering matters for cleanup:
        # 1. thread.started → worker.run (kick off the work)
        # 2. worker.line_output → relay to UI
        # 3. worker.finished → store result and ask thread to quit
        # 4. thread.finished → clean up worker and thread safely
        thread.started.connect(worker.run)
        worker.line_output.connect(self._relay_output)
        worker.finished.connect(self._store_result)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thread_finished)

        self._worker = worker
        self._worker_thread = thread
        self._pending_result: Optional[CommandResult] = None
        self._update_button_states()

        thread.start()

    def _store_result(self, result: CommandResult):
        """Stash the result so _on_thread_finished can use it."""
        self._pending_result = result

    def _on_thread_finished(self):
        """Clean up worker and thread after the thread has fully stopped."""
        result = self._pending_result
        self._pending_result = None

        # Clean up: move worker back to main thread before deletion
        if self._worker is not None:
            self._worker.moveToThread(self.thread())
            self._worker.deleteLater()
            self._worker = None
        if self._worker_thread is not None:
            self._worker_thread.deleteLater()
            self._worker_thread = None

        if result is not None:
            self._on_operation_finished(result)

    def _on_operation_finished(self, result: CommandResult):
        """Handle completion of a background terraform operation."""

        if result.success:
            self.status_bar.showMessage(
                f"terraform {result.command} completed successfully"
            )
            if result.command == "init":
                self._init_done = True
                self._refresh_workspace_info()
        else:
            self.status_bar.showMessage(
                f"terraform {result.command} failed (exit code {result.exit_code})"
            )
            # Show stderr in output if it wasn't already streamed
            if result.stderr and result.stderr not in (self.output_viewer.get_text()):
                self.output_viewer.append_output(result.stderr)

        self._update_button_states()

    def _on_cancel(self):
        """Cancel the running terraform operation."""
        if self.terraform_runner:
            self.terraform_runner.cancel()
        self.status_bar.showMessage("Cancelling...")

    def _on_apply_clicked(self):
        """Show confirmation dialog (if enabled), then run terraform apply."""
        if self.settings.get("confirmations.apply", True):
            workspace = self._current_workspace()
            dialog = ConfirmDialog(
                operation="apply",
                details={"workspace": workspace},
                parent=self,
            )
            if dialog.exec() != ConfirmDialog.DialogCode.Accepted:
                return
        self._run_operation("apply")

    def _on_destroy_clicked(self):
        """Show confirmation dialog (if enabled), then run terraform destroy."""
        if self.settings.get("confirmations.destroy", True):
            workspace = self._current_workspace()
            dialog = ConfirmDialog(
                operation="destroy",
                details={"workspace": workspace},
                parent=self,
            )
            if dialog.exec() != ConfirmDialog.DialogCode.Accepted:
                return
        self._run_operation("destroy")

    def _current_workspace(self) -> str:
        """Return the current workspace name from the manager."""
        if self.workspace_manager:
            return self.workspace_manager.get_current_workspace()
        return "default"

    def _update_info_label(self):
        """Update the project info bar with workspace and path."""
        if not self.current_project_path:
            self._info_label.setText("No project loaded")
            return
        workspace = self._current_workspace()
        self._info_label.setText(
            f"Workspace: {workspace}  |  Project: {self.current_project_path}"
        )

    def _refresh_workspace_info(self):
        """Refresh workspace info from terraform and update the info bar."""
        self._update_info_label()

    def _on_new_workspace(self):
        """Open dialog to create a new workspace."""
        from .dialogs.workspace_dialog import WorkspaceDialog

        dialog = WorkspaceDialog("create", parent=self)
        if dialog.exec() == WorkspaceDialog.DialogCode.Accepted:
            name = dialog.workspace_name()
            if name and self.workspace_manager:
                success = self.workspace_manager.create_workspace(name)
                if success:
                    if self.project_manager:
                        self.project_manager.set_last_workspace(name)
                    self._update_info_label()

    def _on_delete_workspace(self):
        """Open dialog to confirm workspace deletion."""
        from .dialogs.workspace_dialog import WorkspaceDialog

        current = self._current_workspace()
        if not current or current == "default":
            QMessageBox.information(
                self, "Cannot Delete",
                "The default workspace cannot be deleted.",
            )
            return

        dialog = WorkspaceDialog("delete", workspace_name_value=current, parent=self)
        if dialog.exec() == WorkspaceDialog.DialogCode.Accepted:
            if self.workspace_manager:
                self.workspace_manager.switch_workspace("default")
                self.workspace_manager.delete_workspace(current)
                if self.project_manager:
                    self.project_manager.set_last_workspace("default")
                self._update_info_label()

    # ------------------------------------------------------------------
    # Project loading
    # ------------------------------------------------------------------

    def _check_terraform_installed(self):
        """Check if Terraform is installed and show warning if not."""
        terraform_binary = self.settings.get("terraform_binary", "terraform")
        is_installed, version = validate_terraform_installed(terraform_binary)

        if not is_installed:
            logger.warning("Terraform not found in PATH")
            self.status_bar.showMessage(
                "Terraform not found. Install or configure path in Settings."
            )
        else:
            logger.info(f"Terraform found: {version}")

    def _try_load_last_project(self):
        """Try to load the last opened project."""
        last_project = self.settings.get_last_project()

        if last_project and os.path.exists(last_project):
            try:
                self._load_project(last_project)
            except Exception as e:
                logger.error(f"Failed to load last project: {e}")
                self.status_bar.showMessage(f"Last project not found: {last_project}")

    def _on_browse_project(self):
        """Handle Browse button click."""
        project_path = QFileDialog.getExistingDirectory(
            self,
            "Select Terraform Project Directory",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly,
        )

        if not project_path:
            return

        try:
            self._load_project(project_path)
        except Exception as e:
            QMessageBox.critical(
                self, "Error Loading Project",
                f"Failed to load project:\n{str(e)}",
            )

    def _load_project(self, project_path: str):
        """
        Load a Terraform project.

        Validates path, parses variables, populates the variables panel,
        and creates a TerraformRunner instance.

        Raises:
            ValueError: If path is unsafe or not a Terraform project.
        """
        try:
            safe_path = InputSanitizer.sanitize_path(project_path)
        except SecurityError as e:
            raise ValueError(f"Unsafe project path: {e}")

        if not validators.validate_project_is_terraform(safe_path):
            raise ValueError(
                "Directory does not appear to be a Terraform project (no .tf files found)"
            )

        # Detect if project has already been initialized (.terraform dir exists)
        self._init_done = os.path.isdir(os.path.join(safe_path, ".terraform"))
        self.current_project_path = safe_path

        # Project manager (persistence)
        self.project_manager = ProjectManager(safe_path)
        self.project_manager.load()

        # Parser
        self.terraform_parser = TerraformParser(safe_path)

        # Runner
        terraform_binary = self.settings.get("terraform_binary", "terraform")
        debug = self.debug_checkbox.isChecked()
        try:
            self.terraform_runner = TerraformRunner(
                project_path=safe_path,
                terraform_binary=terraform_binary,
                debug=debug,
            )
        except SecurityError as e:
            raise ValueError(f"Failed to create runner: {e}")

        # Workspace manager
        try:
            self.workspace_manager = WorkspaceManager(
                project_path=safe_path,
                terraform_binary=terraform_binary,
            )
        except Exception as e:
            logger.warning(f"Workspace manager init failed: {e}")
            self.workspace_manager = None

        # State manager
        try:
            self.state_manager = StateManager(
                project_path=safe_path,
                terraform_binary=terraform_binary,
            )
        except Exception as e:
            logger.warning(f"State manager init failed: {e}")
            self.state_manager = None

        # Parse variables and populate panel
        try:
            variables = self.terraform_parser.parse_variables()
            saved_values = self.project_manager._state.get("variables", {})
            self.variables_panel.load_variables(variables, saved_values)

            var_count = len(variables)
            sensitive_count = sum(1 for v in variables if v.sensitive)
            logger.info(f"Parsed {var_count} variables ({sensitive_count} sensitive)")

            self.status_bar.showMessage(
                f"Project loaded | Variables: {var_count} ({sensitive_count} sensitive) | "
                f"Workspace: {self.project_manager.get_last_workspace()}"
            )
        except Exception as e:
            logger.error(f"Failed to parse variables: {e}")
            QMessageBox.warning(
                self, "Parse Warning",
                f"Project loaded but failed to parse some variables:\n{str(e)}",
            )

        self._update_button_states()
        self._update_info_label()

        # Persist
        self.settings.add_recent_project(safe_path)
        self.settings.set_last_project(safe_path)
        self.settings.save()

        logger.info(f"Loaded project: {safe_path}")

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _on_edit_project(self):
        """Open project in configured external editor."""
        if not self.current_project_path:
            return

        editor_command = self.settings.get("editor_command", "code")

        try:
            import subprocess
            from ..utils import subprocess_creation_flags
            subprocess.Popen(
                [editor_command, self.current_project_path],
                creationflags=subprocess_creation_flags(),
            )
            logger.info(f"Opened project in {editor_command}")
        except Exception as e:
            logger.error(f"Failed to open editor: {e}")
            QMessageBox.critical(
                self, "Editor Error",
                f"Failed to open project in editor:\n{str(e)}\n\n"
                f"Make sure '{editor_command}' is installed and in PATH.",
            )

    def _show_about(self):
        """Show About dialog."""
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
    # Import / Export .tfvars
    # ------------------------------------------------------------------

    def _on_import_tfvars(self):
        """Import variable values from a .tfvars file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import .tfvars File",
            self.current_project_path or os.path.expanduser("~"),
            "Terraform Variable Files (*.tfvars *.tfvars.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            values = TfvarsHandler.parse_tfvars(file_path)
            count = self.variables_panel.set_values(values)
            self.status_bar.showMessage(
                f"Imported {count} variable(s) from {os.path.basename(file_path)}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Import Error",
                f"Failed to import .tfvars file:\n{str(e)}",
            )

    def _on_export_tfvars(self):
        """Export non-sensitive variable values to a .tfvars file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export .tfvars File",
            os.path.join(
                self.current_project_path or os.path.expanduser("~"),
                "terraform.tfvars",
            ),
            "Terraform Variable Files (*.tfvars);;All Files (*)",
        )
        if not file_path:
            return

        try:
            values = self.variables_panel.get_non_sensitive_values()
            sensitive = self.variables_panel.get_sensitive_names()
            TfvarsHandler.write_tfvars(file_path, values, sensitive)
            self.status_bar.showMessage(
                f"Exported {len(values)} variable(s) to {os.path.basename(file_path)}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Export Error",
                f"Failed to export .tfvars file:\n{str(e)}",
            )

    # ------------------------------------------------------------------
    # Recent projects
    # ------------------------------------------------------------------

    def _rebuild_recent_menu(self):
        """Rebuild the Recent Projects submenu."""
        self._recent_menu.clear()
        recent = self.settings.get_recent_projects()

        if not recent:
            placeholder = QAction("(No recent projects)", self)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)
            return

        for path in recent:
            action = QAction(path, self)
            action.triggered.connect(lambda checked, p=path: self._open_recent_project(p))
            self._recent_menu.addAction(action)

        self._recent_menu.addSeparator()
        clear_action = QAction("Clear Recent Projects", self)
        clear_action.triggered.connect(self._clear_recent_projects)
        self._recent_menu.addAction(clear_action)

    def _open_recent_project(self, path: str):
        """Open a project from the recent projects list."""
        if not os.path.exists(path):
            QMessageBox.warning(
                self, "Project Not Found",
                f"The project directory no longer exists:\n{path}",
            )
            return
        try:
            self._load_project(path)
        except Exception as e:
            QMessageBox.critical(
                self, "Error Loading Project",
                f"Failed to load project:\n{str(e)}",
            )

    def _clear_recent_projects(self):
        """Clear the recent projects list."""
        self.settings.set("recent_projects", [])
        self.settings.save()

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def _on_preferences(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self.settings, parent=self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            # Re-check terraform availability with possibly changed binary
            self._check_terraform_installed()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _on_refresh_project(self):
        """Re-parse variables and refresh workspace list."""
        if not self.current_project_path:
            return

        # Re-parse variables
        if self.terraform_parser:
            try:
                variables = self.terraform_parser.parse_variables()
                current_values = self.variables_panel.get_non_sensitive_values()
                self.variables_panel.load_variables(variables, current_values)
            except Exception as e:
                logger.error(f"Failed to refresh variables: {e}")

        self._update_info_label()
        self.status_bar.showMessage("Project refreshed")

    # ------------------------------------------------------------------
    # State viewer
    # ------------------------------------------------------------------

    def _get_or_create_state_dialog(self):
        """Get or create the state viewer dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout

        if self._state_dialog is not None and self._state_dialog.isVisible():
            return self._state_dialog

        dialog = QDialog(self)
        dialog.setWindowTitle("Terraform State")
        dialog.resize(700, 500)

        layout = QVBoxLayout(dialog)
        viewer = StateViewerWidget()
        layout.addWidget(viewer)

        if self.state_manager:
            viewer.set_manager(self.state_manager)

        dialog._viewer = viewer
        self._state_dialog = dialog
        return dialog

    def _show_state_viewer(self):
        """Open the state viewer dialog showing Resources."""
        dialog = self._get_or_create_state_dialog()
        dialog._viewer._resources_button.setChecked(True)
        dialog._viewer._on_view_toggled(0)
        dialog.show()
        dialog.raise_()

    def _show_outputs_viewer(self):
        """Open the state viewer dialog showing Outputs."""
        dialog = self._get_or_create_state_dialog()
        dialog._viewer._outputs_button.setChecked(True)
        dialog._viewer._on_view_toggled(1)
        dialog.show()
        dialog.raise_()

    def closeEvent(self, event):
        """Save state and close."""
        self.settings.set("window.width", self.width())
        self.settings.set("window.height", self.height())
        self.settings.set("window.maximized", self.isMaximized())
        self.settings.save()

        # Persist non-sensitive variable values
        if self.project_manager:
            non_sensitive = self.variables_panel.get_non_sensitive_values()
            for name, value in non_sensitive.items():
                self.project_manager.set_variable_value(name, value)
            self.project_manager.save()

        logger.info("Application closing")
        event.accept()
