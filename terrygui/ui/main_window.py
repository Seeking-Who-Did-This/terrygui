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
    QLabel, QPushButton, QLineEdit, QFileDialog,
    QStatusBar, QMessageBox, QCheckBox, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QAction

from ..config import Settings
from ..core import TerraformParser, ProjectManager, TerraformRunner, CommandResult
from ..utils import validate_terraform_installed, validators
from ..security import InputSanitizer, SecurityError

from .widgets.variable_input import VariablesPanel
from .widgets.output_viewer import OutputViewerWidget
from .dialogs.confirm_dialog import ConfirmDialog

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

        # --- Project selector row ---
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Project:"))

        self.project_path_edit = QLineEdit()
        self.project_path_edit.setReadOnly(True)
        self.project_path_edit.setPlaceholderText("No project loaded")
        project_layout.addWidget(self.project_path_edit)

        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self._on_browse_project)
        project_layout.addWidget(self.browse_button)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self._on_edit_project)
        self.edit_button.setEnabled(False)
        project_layout.addWidget(self.edit_button)

        main_layout.addLayout(project_layout)

        # --- Variables panel — scales with window, capped to content height ---
        self.variables_panel = VariablesPanel()
        main_layout.addWidget(self.variables_panel, stretch=1)

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
        self.init_button.setToolTip("Run terraform init")
        self.init_button.clicked.connect(lambda: self._run_operation("init"))
        buttons_layout.addWidget(self.init_button)

        self.validate_button = QPushButton("Validate")
        self.validate_button.setToolTip("Run terraform validate")
        self.validate_button.clicked.connect(lambda: self._run_operation("validate"))
        buttons_layout.addWidget(self.validate_button)

        self.plan_button = QPushButton("Plan")
        self.plan_button.setToolTip("Run terraform plan")
        self.plan_button.clicked.connect(lambda: self._run_operation("plan"))
        buttons_layout.addWidget(self.plan_button)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Run terraform apply (with confirmation)")
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

        open_action = QAction("&Open Project...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_browse_project)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu (placeholder for Phase 5)
        view_menu = menubar.addMenu("&View")
        view_menu.setEnabled(False)

        # Workspace menu (placeholder for Phase 4)
        workspace_menu = menubar.addMenu("&Workspace")
        workspace_menu.setEnabled(False)

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

        # Disable browse/edit while running to prevent project switch mid-operation
        self.browse_button.setEnabled(not running)
        self.edit_button.setEnabled(has_project and not running)

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
        """Show confirmation dialog, then run terraform apply."""
        workspace = "default"
        if self.project_manager:
            workspace = self.project_manager.get_last_workspace()

        dialog = ConfirmDialog(
            operation="apply",
            details={"workspace": workspace},
            parent=self,
        )
        if dialog.exec() == ConfirmDialog.DialogCode.Accepted:
            self._run_operation("apply")

    def _on_destroy_clicked(self):
        """Show confirmation dialog, then run terraform destroy."""
        workspace = "default"
        if self.project_manager:
            workspace = self.project_manager.get_last_workspace()

        dialog = ConfirmDialog(
            operation="destroy",
            details={"workspace": workspace},
            parent=self,
        )
        if dialog.exec() == ConfirmDialog.DialogCode.Accepted:
            self._run_operation("destroy")

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
        self.project_path_edit.setText(safe_path)

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

        self.edit_button.setEnabled(True)
        self._update_button_states()

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
            subprocess.Popen([editor_command, self.current_project_path])
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
