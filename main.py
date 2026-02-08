#!/usr/bin/env python3
"""
TerryGUI - Main entry point.

Launches the Qt application.
"""

import sys
import logging
from PySide6.QtWidgets import QApplication

from terrygui.ui import MainWindow
from terrygui.utils import setup_logging


def main():
    """Main entry point for TerryGUI."""
    # Set up logging
    setup_logging(log_level="INFO", log_file=True)
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("TerryGUI v1.0.0 starting...")
    logger.info("=" * 60)
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("TerryGUI")
    app.setOrganizationName("TerryGUI")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    exit_code = app.exec()
    
    logger.info("TerryGUI exiting")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
