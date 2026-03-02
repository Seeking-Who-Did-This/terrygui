"""
Per-project pane widget for TerryGUI.

Each open project lives in one ProjectPane instance.  MainWindow hosts
multiple panes via a QTabWidget and delegates all project-specific work here.
"""

import os
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QCheckBox, QFrame, QDialog,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject

from ...config import Settings
from ...core import (
    TerraformParser, ProjectManager, TerraformRunner,
    CommandResult, WorkspaceManager, StateManager,
)
from ...core.tfvars_handler import TfvarsHandler
from ...utils import validators
from ...security import InputSanitizer, SecurityError

from .variable_input import VariablesPanel
from .output_viewer import OutputViewerWidget
from .state_viewer import StateViewerWidget
from ..dialogs.confirm_dialog import ConfirmDialog

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


# ---------------------------------------------------------------------------
# ProjectPane
# ---------------------------------------------------------------------------

class ProjectPane(QWidget):
    """
    Self-contained per-project widget.

    Hosts variable inputs, output viewer, and operation buttons for one
    Terraform project.  Multiple instances live in MainWindow's QTabWidget.
    """

    # Relay to MainWindow's status bar (active pane only)
    status_message = Signal(str)
    # Emitted after a project is successfully loaded (for dup detection + tab rename)
    project_loaded = Signal(str)
    # Emitted when the tab label should change (project load or workspace switch)
    tab_title_changed = Signal(str)

    # Internal signal for thread-safe output relay
    _relay_output = Signal(str)

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)

        self.settings = settings

        # Per-project state
        self.current_project_path: Optional[str] = None
        self.project_manager: Optional[ProjectManager] = None
        self.terraform_parser: Optional[TerraformParser] = None
        self.terraform_runner: Optional[TerraformRunner] = None
        self.workspace_manager: Optional[WorkspaceManager] = None
        self.state_manager: Optional[StateManager] = None
        self._state_dialog: Optional[QDialog] = None

        # Variable counts (for info bar)
        self._var_count: int = 0
        self._sensitive_count: int = 0

        # Background operation state
        self._worker: Optional[_OperationWorker] = None
        self._worker_thread: Optional[QThread] = None
        self._init_done = False
        self._pending_result: Optional[CommandResult] = None

        self._init_ui()
        self._update_button_states()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Variables panel
        self.variables_panel = VariablesPanel()
        main_layout.addWidget(self.variables_panel, stretch=1)

        # Visual divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(divider)

        # Output viewer
        self.output_viewer = OutputViewerWidget()
        self.output_viewer.setMinimumHeight(120)
        self.output_viewer.setMaximumHeight(400)
        main_layout.addWidget(self.output_viewer)

        # Operation buttons row
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

        # Thread-safe output relay
        self._relay_output.connect(self.output_viewer.append_output)

    # ------------------------------------------------------------------
    # Button state machine
    # ------------------------------------------------------------------

    def _update_button_states(self):
        running = self._worker_thread is not None and self._worker_thread.isRunning()
        has_project = self.current_project_path is not None

        self.init_button.setEnabled(has_project and not running)
        self.validate_button.setEnabled(has_project and self._init_done and not running)
        self.plan_button.setEnabled(has_project and self._init_done and not running)
        self.apply_button.setEnabled(has_project and self._init_done and not running)
        self.destroy_button.setEnabled(has_project and self._init_done and not running)
        self.cancel_button.setEnabled(running)

    # ------------------------------------------------------------------
    # Terraform operations
    # ------------------------------------------------------------------

    def _run_operation(self, operation: str):
        """Start a terraform operation in a background thread."""
        if self.terraform_runner is None or self._worker_thread is not None:
            return

        self.output_viewer.clear()
        self.output_viewer.set_label(f"Output — terraform {operation}")
        self.status_message.emit(f"Running terraform {operation}...")

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
            auto_approve = True

        worker = _OperationWorker(
            self.terraform_runner, operation,
            variables=variables, var_types=var_types,
            auto_approve=auto_approve,
        )
        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.line_output.connect(self._relay_output)
        worker.finished.connect(self._store_result)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thread_finished)

        self._worker = worker
        self._worker_thread = thread
        self._pending_result = None
        self._update_button_states()

        thread.start()

    def _store_result(self, result: CommandResult):
        self._pending_result = result

    def _on_thread_finished(self):
        result = self._pending_result
        self._pending_result = None

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
        if result.success:
            self.status_message.emit(
                f"terraform {result.command} completed successfully"
            )
            if result.command == "init":
                self._init_done = True
                self._refresh_workspace_info()
        else:
            self.status_message.emit(
                f"terraform {result.command} failed (exit code {result.exit_code})"
            )
            if result.stderr and result.stderr not in self.output_viewer.get_text():
                self.output_viewer.append_output(result.stderr)

        self._update_button_states()

    def _on_cancel(self):
        if self.terraform_runner:
            self.terraform_runner.cancel()
        self.status_message.emit("Cancelling...")

    def _on_apply_clicked(self):
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
        if self.workspace_manager:
            return self.workspace_manager.get_current_workspace()
        return "default"

    def get_tab_title(self) -> str:
        """Return nickname if set, otherwise the project folder name."""
        if self.project_manager:
            nick = self.project_manager.get_nickname()
            if nick:
                return nick
        if self.current_project_path:
            return os.path.basename(self.current_project_path)
        return "New Tab"

    def set_nickname(self, name: str):
        """Set or clear the project nickname and persist it immediately."""
        if not self.project_manager:
            return
        self.project_manager.set_nickname(name)
        self.project_manager.save()
        self._update_info()

    def _tab_title_with_workspace(self) -> str:
        """Tab label incorporating workspace prefix when not on default."""
        title = self.get_tab_title()
        workspace = self._current_workspace()
        if workspace and workspace != "default":
            return f"[{workspace}] {title}"
        return title

    def _update_info(self):
        if self.current_project_path:
            self.tab_title_changed.emit(self._tab_title_with_workspace())
            workspace = self._current_workspace()
            nick = self.project_manager.get_nickname() if self.project_manager else ""
            path_part = f"{nick}  —  {self.current_project_path}" if nick else self.current_project_path
            self.status_message.emit(
                f"Workspace: {workspace}  |  {self._var_count} variables ({self._sensitive_count} sensitive)  |  {path_part}"
            )

    def _refresh_workspace_info(self):
        self._update_info()

    def _on_new_workspace(self):
        from ..dialogs.workspace_dialog import WorkspaceDialog

        dialog = WorkspaceDialog("create", parent=self)
        if dialog.exec() == WorkspaceDialog.DialogCode.Accepted:
            name = dialog.workspace_name()
            if name and self.workspace_manager:
                success = self.workspace_manager.create_workspace(name)
                if success:
                    if self.project_manager:
                        self.project_manager.set_last_workspace(name)
                    self._update_info()

    def _on_delete_workspace(self):
        from ..dialogs.workspace_dialog import WorkspaceDialog

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
                self._update_info()

    # ------------------------------------------------------------------
    # State viewer
    # ------------------------------------------------------------------

    def _get_or_create_state_dialog(self):
        from PySide6.QtWidgets import QVBoxLayout as _QVBoxLayout

        if self._state_dialog is not None and self._state_dialog.isVisible():
            return self._state_dialog

        dialog = QDialog(self)
        dialog.setWindowTitle("Terraform State")
        dialog.resize(700, 500)

        layout = _QVBoxLayout(dialog)
        viewer = StateViewerWidget()
        layout.addWidget(viewer)

        if self.state_manager:
            viewer.set_manager(self.state_manager)

        dialog._viewer = viewer
        self._state_dialog = dialog
        return dialog

    def _show_state_viewer(self):
        dialog = self._get_or_create_state_dialog()
        dialog._viewer._resources_button.setChecked(True)
        dialog._viewer._on_view_toggled(0)
        dialog.show()
        dialog.raise_()

    def _show_outputs_viewer(self):
        dialog = self._get_or_create_state_dialog()
        dialog._viewer._outputs_button.setChecked(True)
        dialog._viewer._on_view_toggled(1)
        dialog.show()
        dialog.raise_()

    # ------------------------------------------------------------------
    # Project loading
    # ------------------------------------------------------------------

    def load_project(self, project_path: str):
        """Public entry point — loads a project into this pane."""
        self._load_project(project_path)

    def _load_project(self, project_path: str):
        """
        Load a Terraform project.

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

        self._init_done = os.path.isdir(os.path.join(safe_path, ".terraform"))
        self.current_project_path = safe_path

        self.project_manager = ProjectManager(safe_path)
        self.project_manager.load()

        self.terraform_parser = TerraformParser(safe_path)

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

        try:
            self.workspace_manager = WorkspaceManager(
                project_path=safe_path,
                terraform_binary=terraform_binary,
            )
        except Exception as e:
            logger.warning(f"Workspace manager init failed: {e}")
            self.workspace_manager = None

        try:
            self.state_manager = StateManager(
                project_path=safe_path,
                terraform_binary=terraform_binary,
            )
        except Exception as e:
            logger.warning(f"State manager init failed: {e}")
            self.state_manager = None

        try:
            variables = self.terraform_parser.parse_variables()
            saved_values = self.project_manager._state.get("variables", {})
            self.variables_panel.load_variables(variables, saved_values)

            var_count = len(variables)
            sensitive_count = sum(1 for v in variables if v.sensitive)
            self._var_count = var_count
            self._sensitive_count = sensitive_count
            logger.info(f"Parsed {var_count} variables ({sensitive_count} sensitive)")

            nick = self.project_manager.get_nickname()
            path_part = f"{nick}  —  {safe_path}" if nick else safe_path
            self.status_message.emit(
                f"Project loaded  |  {var_count} variables ({sensitive_count} sensitive)  |  "
                f"Workspace: {self.project_manager.get_last_workspace()}  |  {path_part}"
            )
        except Exception as e:
            logger.error(f"Failed to parse variables: {e}")
            QMessageBox.warning(
                self, "Parse Warning",
                f"Project loaded but failed to parse some variables:\n{str(e)}",
            )

        self._update_button_states()
        self._update_info()

        self.settings.add_recent_project(safe_path)
        self.settings.set_last_project(safe_path)
        self.settings.save()

        self.project_loaded.emit(safe_path)
        self.tab_title_changed.emit(self.get_tab_title())

        logger.info(f"Loaded project: {safe_path}")

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _on_edit_project(self):
        if not self.current_project_path:
            return

        editor_command = self.settings.get("editor_command", "code")
        try:
            import subprocess
            from ...utils import subprocess_creation_flags
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

    def _on_refresh_project(self):
        if not self.current_project_path:
            return

        if self.terraform_parser:
            try:
                variables = self.terraform_parser.parse_variables()
                current_values = self.variables_panel.get_non_sensitive_values()
                self.variables_panel.load_variables(variables, current_values)
            except Exception as e:
                logger.error(f"Failed to refresh variables: {e}")

        self._update_info()
        self.status_message.emit("Project refreshed")

    # ------------------------------------------------------------------
    # Import / Export .tfvars
    # ------------------------------------------------------------------

    def _on_import_tfvars(self):
        from PySide6.QtWidgets import QFileDialog
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
            self.status_message.emit(
                f"Imported {count} variable(s) from {os.path.basename(file_path)}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Import Error",
                f"Failed to import .tfvars file:\n{str(e)}",
            )

    def _on_export_tfvars(self):
        from PySide6.QtWidgets import QFileDialog
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
            self.status_message.emit(
                f"Exported {len(values)} variable(s) to {os.path.basename(file_path)}"
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Export Error",
                f"Failed to export .tfvars file:\n{str(e)}",
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_state(self):
        """Persist non-sensitive vars + project manager state. Called on tab close."""
        if self.project_manager:
            non_sensitive = self.variables_panel.get_non_sensitive_values()
            for name, value in non_sensitive.items():
                self.project_manager.set_variable_value(name, value)
            self.project_manager.save()

    def is_operation_running(self) -> bool:
        """Return True if a background operation is in progress."""
        return self._worker_thread is not None and self._worker_thread.isRunning()
