#!/usr/bin/env python3
"""
TerryGUI - Main entry point.

Launches the Qt application.
"""

import sys
import os
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from terrygui.ui import MainWindow
from terrygui.utils import setup_logging


def _app_icon() -> QIcon:
    """Return the application icon, resolved whether running from source or frozen binary."""
    if getattr(sys, "frozen", False):
        # PyInstaller unpacks data files next to the executable in _MEIPASS
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(__file__)
    icon_path = os.path.join(base, "terrygui", "resources", "icon.png")
    return QIcon(icon_path)


def main():
    """Main entry point for TerryGUI."""
    # Set up logging
    setup_logging(log_level="INFO", log_file=True)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("TerryGUI starting...")
    logger.info("=" * 60)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("TerryGUI")
    app.setOrganizationName("TerryGUI")
    app.setWindowIcon(_app_icon())
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    exit_code = app.exec()
    
    logger.info("TerryGUI exiting")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
