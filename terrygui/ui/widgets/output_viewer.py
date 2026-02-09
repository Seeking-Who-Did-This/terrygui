"""
Output viewer widget for TerryGUI.

Displays Terraform command output with ANSI color rendering,
auto-scroll, search, and copy-to-clipboard support.
"""

import re
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLineEdit, QLabel, QApplication,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QTextCursor, QColor, QTextCharFormat, QFont

logger = logging.getLogger(__name__)

# Basic ANSI color code mapping (foreground only)
ANSI_COLORS = {
    "30": QColor("#000000"),  # black
    "31": QColor("#cc0000"),  # red
    "32": QColor("#00cc00"),  # green
    "33": QColor("#cccc00"),  # yellow
    "34": QColor("#0000cc"),  # blue
    "35": QColor("#cc00cc"),  # magenta
    "36": QColor("#00cccc"),  # cyan
    "37": QColor("#cccccc"),  # white
    "90": QColor("#666666"),  # bright black
    "91": QColor("#ff3333"),  # bright red
    "92": QColor("#33ff33"),  # bright green
    "93": QColor("#ffff33"),  # bright yellow
    "94": QColor("#3333ff"),  # bright blue
    "95": QColor("#ff33ff"),  # bright magenta
    "96": QColor("#33ffff"),  # bright cyan
    "97": QColor("#ffffff"),  # bright white
}

# Regex to match ANSI escape sequences
ANSI_ESCAPE = re.compile(r'\x1b\[([0-9;]*)m')


class OutputViewerWidget(QWidget):
    """
    Displays streaming Terraform output with ANSI color rendering.

    Features:
    - ANSI color code parsing and display
    - Auto-scroll to follow output
    - Copy to clipboard
    - Clear output
    - Search within output
    - Line count limit (default 10,000)
    """

    MAX_LINES = 10000

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._line_count = 0
        self._auto_scroll = True
        self._current_format = QTextCharFormat()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        self._label = QLabel("Output")
        self._label.setStyleSheet("font-weight: bold; padding: 4px;")
        toolbar.addWidget(self._label)

        toolbar.addStretch()

        # Search field
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search output...")
        self._search_input.setMaximumWidth(200)
        self._search_input.returnPressed.connect(self._on_search)
        toolbar.addWidget(self._search_input)

        self._copy_button = QPushButton("Copy")
        self._copy_button.setToolTip("Copy all output to clipboard")
        self._copy_button.clicked.connect(self._on_copy)
        toolbar.addWidget(self._copy_button)

        self._clear_button = QPushButton("Clear")
        self._clear_button.setToolTip("Clear output")
        self._clear_button.clicked.connect(self.clear)
        toolbar.addWidget(self._clear_button)

        layout.addLayout(toolbar)

        # Output text area
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("Consolas", 10))
        self._text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._text_edit)

    @Slot(str)
    def append_output(self, text: str):
        """
        Append a line of output, parsing any ANSI color codes.

        Args:
            text: A single line of output (may contain ANSI escapes).
        """
        # Enforce line limit
        if self._line_count >= self.MAX_LINES:
            return

        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        if self._line_count > 0:
            cursor.insertText("\n")

        self._insert_ansi_text(cursor, text)
        self._line_count += 1

        if self._auto_scroll:
            self._text_edit.setTextCursor(cursor)
            self._text_edit.ensureCursorVisible()

    def _insert_ansi_text(self, cursor: QTextCursor, text: str):
        """Parse ANSI escape codes and insert formatted text segments."""
        last_end = 0

        for match in ANSI_ESCAPE.finditer(text):
            # Insert text before this escape sequence
            start = match.start()
            if start > last_end:
                cursor.insertText(text[last_end:start], self._current_format)

            # Update format based on ANSI codes
            codes = match.group(1).split(";")
            self._apply_ansi_codes(codes)
            last_end = match.end()

        # Insert remaining text after last escape
        if last_end < len(text):
            cursor.insertText(text[last_end:], self._current_format)

    def _apply_ansi_codes(self, codes: list[str]):
        """Apply ANSI SGR codes to the current text format."""
        for code in codes:
            if code in ("0", ""):
                # Reset
                self._current_format = QTextCharFormat()
            elif code == "1":
                self._current_format.setFontWeight(QFont.Weight.Bold)
            elif code == "3":
                self._current_format.setFontItalic(True)
            elif code == "4":
                self._current_format.setFontUnderline(True)
            elif code in ANSI_COLORS:
                self._current_format.setForeground(ANSI_COLORS[code])

    def clear(self):
        """Clear all output."""
        self._text_edit.clear()
        self._line_count = 0
        self._current_format = QTextCharFormat()

    def set_label(self, text: str):
        """Set the output header label text."""
        self._label.setText(text)

    def _on_copy(self):
        """Copy all output text to clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._text_edit.toPlainText())

    def _on_search(self):
        """Find and highlight the next occurrence of the search text."""
        query = self._search_input.text()
        if not query:
            return

        # Search from current cursor position
        found = self._text_edit.find(query)
        if not found:
            # Wrap around to the beginning
            cursor = self._text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._text_edit.setTextCursor(cursor)
            self._text_edit.find(query)

    def get_text(self) -> str:
        """Return all output as plain text."""
        return self._text_edit.toPlainText()

    def line_count(self) -> int:
        """Return the current number of output lines."""
        return self._line_count
