"""
README markdown viewer widget for TerryGUI.

Renders a project's README.md as formatted markdown using Qt's native
QTextBrowser markdown support (Qt 5.14+).
"""

import os
import re
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextBrowser, QSizePolicy,
)

logger = logging.getLogger(__name__)

# README filenames to check, in priority order.
_README_NAMES = ("README.md", "readme.md", "Readme.md", "README.MD")


class ReadmeViewerWidget(QWidget):
    """
    Renders a project README.md as formatted markdown.

    Call load_readme(project_path) after a project is opened.
    Returns True if a README was found and loaded, False otherwise.
    The caller is responsible for showing/hiding this widget accordingly.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._browser)

    def load_readme(self, project_path: str) -> bool:
        """
        Locate and render README.md from project_path.

        Args:
            project_path: Absolute path to the Terraform project directory.

        Returns:
            True if a README was found and loaded successfully, False otherwise.
        """
        readme_path = self._find_readme(project_path)
        if readme_path is None:
            self.clear()
            return False

        try:
            with open(readme_path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            self._render(content)
            logger.debug(f"Loaded README from {readme_path}")
            return True
        except OSError as e:
            logger.warning(f"Could not read README at {readme_path}: {e}")
            self.clear()
            return False

    def clear(self):
        """Clear the displayed content."""
        self._browser.clear()

    def _render(self, content: str) -> None:
        """Render markdown with proper code block styling.

        Qt's setMarkdown() renders fenced code blocks in monospace but without
        any background or border, making them visually indistinct.  We
        pre-process the markdown to replace fenced code blocks with styled HTML
        <pre> blocks, then call setHtml() so Qt renders them with a visible
        background.  This uses no external dependencies beyond PySide6.
        """
        # Always use a light gray background with dark text for code blocks so
        # they are visually distinct from surrounding prose regardless of whether
        # the application is running in light or dark mode.
        code_bg, code_fg, border = "#e0e0e0", "#1a1a1a", "#b0b0b0"

        # The outer div carries background/border/padding (Qt honours these on
        # block divs reliably).  The inner pre handles monospace + line breaks
        # with no extra margin/padding of its own.
        div_style = (
            f"background-color:{code_bg}; color:{code_fg}; border:1px solid {border};"
            " padding:15px; margin:10px 6px 10px 10px;"
        )
        pre_style = (
            f"color:{code_fg}; margin:0; padding:0; white-space:pre-wrap;"
            " font-family:'Courier New',Courier,monospace; font-size:90%;"
        )

        def replace_fence(m: re.Match) -> str:
            code = m.group(1)
            # Escape HTML special chars inside the block.
            code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return f'<div style="{div_style}"><pre style="{pre_style}">{code}</pre></div>'

        # Replace ```lang\n...\n``` blocks (fenced, with or without lang tag).
        processed = re.sub(
            r"```[^\n]*\n(.*?)```",
            replace_fence,
            content,
            flags=re.DOTALL,
        )
        # Also handle ~~~...~~~ fences.
        processed = re.sub(
            r"~~~[^\n]*\n(.*?)~~~",
            replace_fence,
            processed,
            flags=re.DOTALL,
        )

        # Pass the result to Qt.  Sections without code blocks are still valid
        # markdown mixed with HTML fragments, which setMarkdown() ignores but
        # setHtml() would mangle.  So we convert the whole thing to HTML by
        # wrapping non-HTML chunks — the simplest approach is just setHtml with
        # the raw mixed content inside a body, which QTextBrowser handles fine.
        css = (
            "body { font-family: sans-serif; margin:4px; }"
            f"code {{ font-family:'Courier New',Courier,monospace; font-size:90%;"
            f" background-color:{code_bg}; color:{code_fg}; padding:1px 4px; border-radius:3px; }}"
            "table { border-collapse:collapse; margin:6px 0; }"
            f"th,td {{ border:1px solid {border}; padding:4px 8px; }}"
        )

        # Re-render the non-code-block portions through Qt markdown so that
        # headings, bold, lists, etc. are still formatted correctly.
        # Strategy: split on our injected <div> blocks, render each text chunk
        # as markdown, then reassemble.
        parts = re.split(r"(<div\b.*?</div>)", processed, flags=re.DOTALL)
        rendered_parts = []
        for part in parts:
            if part.startswith("<div"):
                rendered_parts.append(part)
            else:
                from PySide6.QtGui import QTextDocument
                doc = QTextDocument()
                doc.setMarkdown(part)
                # Extract just the body content from Qt's generated HTML.
                inner = doc.toHtml()
                # Qt wraps in <html><body>…</body></html>; extract body content.
                body_match = re.search(r"<body[^>]*>(.*)</body>", inner, re.DOTALL)
                rendered_parts.append(body_match.group(1) if body_match else part)

        html = (
            f"<!DOCTYPE html><html><head><style>{css}</style></head>"
            f"<body>{''.join(rendered_parts)}</body></html>"
        )
        self._browser.setHtml(html)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_readme(project_path: str) -> Optional[str]:
        """Return the path to the first README variant found, or None."""
        for name in _README_NAMES:
            candidate = os.path.join(project_path, name)
            if os.path.isfile(candidate):
                return candidate
        return None
