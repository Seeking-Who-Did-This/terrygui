"""
Main application window for TerryGUI.

This is the primary UI window containing all major components.
"""

import os
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog,
    QStatusBar, QMessageBox, QMenuBar, QMenu
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from ..config import Settings
from ..core import TerraformParser, ProjectManager
from ..utils import validate_terraform_installed, validators
from ..security import InputSanitizer, SecurityError

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main application window.
    """
    
    def __init__(self):
        """Initialize main window."""
        super().__init__()
        
        self.settings = Settings()
        self.current_project_path: Optional[str] = None
        self.project_manager: Optional[ProjectManager] = None
        self.terraform_parser: Optional[TerraformParser] = None
        
        self._init_ui()
        self._check_terraform_installed()
        self._try_load_last_project()
    
    def _init_ui(self):
        """Initialize user interface."""
        self.setWindowTitle("TerryGUI - Terraform Manager")
        
        # Set window size from settings
        width = self.settings.get("window.width", 900)
        height = self.settings.get("window.height", 700)
        self.resize(width, height)
        
        # Create menu bar
        self._create_menu_bar()
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Project selector section
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Project:"))
        
        self.project_path_edit = QLineEdit()
        self.project_path_edit.setReadOnly(True)
        self.project_path_edit.setPlaceholderText("No project loaded")
        project_layout.addWidget(self.project_path_edit)
        
        self.browse_button = QPushButton("📁 Browse")
        self.browse_button.clicked.connect(self._on_browse_project)
        project_layout.addWidget(self.browse_button)
        
        self.edit_button = QPushButton("✏️ Edit")
        self.edit_button.clicked.connect(self._on_edit_project)
        self.edit_button.setEnabled(False)
        project_layout.addWidget(self.edit_button)
        
        main_layout.addLayout(project_layout)
        
        # Placeholder for variables panel (coming soon)
        variables_label = QLabel("Variables panel (coming soon)")
        variables_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        variables_label.setStyleSheet("color: gray; padding: 40px;")
        main_layout.addWidget(variables_label)
        
        # Placeholder for operation buttons (coming soon)
        buttons_label = QLabel("Operation buttons (coming soon)")
        buttons_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons_label.setStyleSheet("color: gray; padding: 20px;")
        main_layout.addWidget(buttons_label)
        
        # Add stretch to push everything to top
        main_layout.addStretch()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
    
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
        
        # View menu (placeholder)
        view_menu = menubar.addMenu("&View")
        view_menu.setEnabled(False)
        
        # Workspace menu (placeholder)
        workspace_menu = menubar.addMenu("&Workspace")
        workspace_menu.setEnabled(False)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _check_terraform_installed(self):
        """Check if Terraform is installed and show warning if not."""
        terraform_binary = self.settings.get("terraform_binary", "terraform")
        is_installed, version = validate_terraform_installed(terraform_binary)
        
        if not is_installed:
            logger.warning("Terraform not found in PATH")
            self.status_bar.showMessage(
                "⚠️ Terraform not found. Install or configure path in Settings."
            )
            # Note: Operation buttons will be disabled until this is resolved
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
        # Open directory dialog
        project_path = QFileDialog.getExistingDirectory(
            self,
            "Select Terraform Project Directory",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not project_path:
            return  # User cancelled
        
        try:
            self._load_project(project_path)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading Project",
                f"Failed to load project:\n{str(e)}"
            )
    
    def _load_project(self, project_path: str):
        """
        Load a Terraform project.
        
        Args:
            project_path: Absolute path to project directory
            
        Raises:
            SecurityError: If path is unsafe
            ValueError: If not a valid Terraform project
        """
        # Validate path
        try:
            safe_path = InputSanitizer.sanitize_path(project_path)
        except SecurityError as e:
            raise ValueError(f"Unsafe project path: {e}")
        
        # Check if it's a Terraform project
        if not validators.validate_project_is_terraform(safe_path):
            raise ValueError("Directory does not appear to be a Terraform project (no .tf files found)")
        
        # Load project
        self.current_project_path = safe_path
        self.project_path_edit.setText(safe_path)
        
        # Initialize project manager
        self.project_manager = ProjectManager(safe_path)
        self.project_manager.load()
        
        # Initialize Terraform parser
        self.terraform_parser = TerraformParser(safe_path)
        
        # Parse variables
        try:
            variables = self.terraform_parser.parse_variables()
            var_count = len(variables)
            sensitive_count = sum(1 for v in variables if v.sensitive)
            
            logger.info(f"Parsed {var_count} variables ({sensitive_count} sensitive)")
            
            # Update status bar
            self.status_bar.showMessage(
                f"Project loaded | Variables: {var_count} ({sensitive_count} sensitive) | "
                f"Workspace: {self.project_manager.get_last_workspace()}"
            )
        except Exception as e:
            logger.error(f"Failed to parse variables: {e}")
            QMessageBox.warning(
                self,
                "Parse Warning",
                f"Project loaded but failed to parse some variables:\n{str(e)}"
            )
        
        # Enable edit button
        self.edit_button.setEnabled(True)
        
        # Save to recent projects and settings
        self.settings.add_recent_project(safe_path)
        self.settings.set_last_project(safe_path)
        self.settings.save()
        
        logger.info(f"Loaded project: {safe_path}")
    
    def _on_edit_project(self):
        """Handle Edit Project button click."""
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
                self,
                "Editor Error",
                f"Failed to open project in editor:\n{str(e)}\n\n"
                f"Make sure '{editor_command}' is installed and in PATH."
            )
    
    def _show_about(self):
        """Show About dialog."""
        from .. import __version__
        
        QMessageBox.about(
            self,
            "About TerryGUI",
            f"<h2>TerryGUI v{__version__}</h2>"
            "<p>A professional Qt-based GUI for managing Terraform projects.</p>"
            "<p>Copyright © 2026 TerryGUI Contributors</p>"
            "<p>Licensed under MIT License</p>"
        )
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Save window geometry
        self.settings.set("window.width", self.width())
        self.settings.set("window.height", self.height())
        self.settings.set("window.maximized", self.isMaximized())
        self.settings.save()
        
        # Save project state if project is loaded
        if self.project_manager:
            self.project_manager.save()
        
        logger.info("Application closing")
        event.accept()
