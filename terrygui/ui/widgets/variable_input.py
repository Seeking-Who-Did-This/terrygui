"""
Variable input widget for TerryGUI.

Provides type-appropriate input fields for Terraform variables with
validation feedback, description tooltips, and sensitive value masking.
"""

import logging
from typing import Any, Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QLineEdit, QCheckBox, QTextEdit, QToolButton,
    QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator, QDoubleValidator

from ...core.terraform_parser import TerraformVariable
from ...security.sanitizer import InputSanitizer, SecurityError

logger = logging.getLogger(__name__)


class VariableInputWidget(QWidget):
    """
    Input widget for a single Terraform variable.

    Renders type-appropriate input controls:
    - string: QLineEdit
    - number: QLineEdit with numeric validation
    - bool: QCheckBox
    - sensitive: QLineEdit with password echo mode
    - list/map/object: QTextEdit with JSON validation
    """

    value_changed = Signal(str)  # Emits variable name when value changes

    def __init__(self, variable: TerraformVariable, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.variable = variable
        self._valid = True
        self._init_ui()
        self._apply_default()

    def _init_ui(self):
        """Build the widget layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Label: variable name (with * if required)
        label_text = self.variable.name
        if self.variable.is_required():
            label_text += " *"
        self.name_label = QLabel(label_text)
        self.name_label.setFixedWidth(180)
        self.name_label.setToolTip(self._build_tooltip())
        layout.addWidget(self.name_label)

        # Type-appropriate input widget
        self._create_input_widget(layout)

        # Validation indicator
        self.validation_label = QLabel("")
        self.validation_label.setFixedWidth(24)
        self.validation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.validation_label)

    def _build_tooltip(self) -> str:
        """Build a tooltip string from variable metadata."""
        parts = []
        if self.variable.description:
            parts.append(self.variable.description)
        parts.append(f"Type: {self.variable.type}")
        if self.variable.default is not None:
            parts.append(f"Default: {self.variable.default}")
        if self.variable.sensitive:
            parts.append("Sensitive: yes (value will not be persisted)")
        if self.variable.is_required():
            parts.append("Required")
        return "\n".join(parts)

    def _create_input_widget(self, layout):
        """Create the appropriate input widget based on variable type."""
        var_type = self.variable.type.lower()

        if self.variable.sensitive:
            self._input = QLineEdit()
            self._input.setEchoMode(QLineEdit.EchoMode.Password)
            self._input.setPlaceholderText("(sensitive)")
            self._input.textChanged.connect(self._on_text_changed)
            layout.addWidget(self._input)

        elif var_type == "bool":
            self._input = QCheckBox()
            self._input.stateChanged.connect(
                lambda: self.value_changed.emit(self.variable.name)
            )
            layout.addWidget(self._input)
            # Add stretch so checkbox doesn't float far right
            layout.addStretch()

        elif var_type == "number":
            self._input = QLineEdit()
            self._input.setPlaceholderText("number")
            self._input.textChanged.connect(self._on_text_changed)
            layout.addWidget(self._input)

        elif var_type in ("list", "map", "object"):
            self._input = QTextEdit()
            self._input.setPlaceholderText(f'{var_type} (JSON format)')
            self._input.setMaximumHeight(80)
            self._input.textChanged.connect(
                lambda: self._on_text_changed(self._input.toPlainText())
            )
            layout.addWidget(self._input)

        else:  # string or unknown
            self._input = QLineEdit()
            self._input.setPlaceholderText("string")
            self._input.textChanged.connect(self._on_text_changed)
            layout.addWidget(self._input)

    def _apply_default(self):
        """Set the input to the variable's default value if present."""
        if self.variable.default is None:
            return

        default = self.variable.default
        var_type = self.variable.type.lower()

        if var_type == "bool":
            checked = default is True or str(default).lower() in ("true", "1")
            self._input.setChecked(checked)
        elif var_type in ("list", "map", "object"):
            import json
            if isinstance(default, str):
                self._input.setPlainText(default)
            else:
                self._input.setPlainText(json.dumps(default, indent=2))
        else:
            self._input.setText(str(default))

    def _on_text_changed(self, text: str):
        """Handle text changes — validate and update indicator."""
        self._validate()
        self.value_changed.emit(self.variable.name)

    def _validate(self) -> bool:
        """Validate current value and update the indicator icon."""
        value = self.get_value()
        var_type = self.variable.type.lower()

        # Empty required field
        if self.variable.is_required() and (value is None or value == ""):
            self._set_validation_state(False, "Required")
            return False

        # Empty optional field is fine
        if value is None or value == "":
            self._set_validation_state(True)
            return True

        try:
            InputSanitizer.sanitize_variable_value(value, var_type)
            self._set_validation_state(True)
            return True
        except SecurityError as e:
            self._set_validation_state(False, str(e))
            return False

    def _set_validation_state(self, valid: bool, message: str = ""):
        """Update the validation indicator."""
        self._valid = valid
        if valid:
            self.validation_label.setText("")
            self.validation_label.setToolTip("")
        else:
            self.validation_label.setText("!")
            self.validation_label.setStyleSheet("color: red; font-weight: bold;")
            self.validation_label.setToolTip(message)

    def get_value(self) -> Any:
        """Return the current value from the input widget."""
        var_type = self.variable.type.lower()

        if var_type == "bool":
            return self._input.isChecked()
        elif var_type in ("list", "map", "object"):
            return self._input.toPlainText().strip()
        else:
            return self._input.text().strip()

    def set_value(self, value: Any):
        """Set the input widget value programmatically."""
        var_type = self.variable.type.lower()

        if var_type == "bool":
            checked = value is True or str(value).lower() in ("true", "1")
            self._input.setChecked(checked)
        elif var_type in ("list", "map", "object"):
            import json
            if isinstance(value, str):
                self._input.setPlainText(value)
            else:
                self._input.setPlainText(json.dumps(value, indent=2))
        else:
            self._input.setText(str(value))

    def is_valid(self) -> bool:
        """Return whether the current value passes validation."""
        return self._validate()


class VariablesPanel(QWidget):
    """
    Scrollable panel containing VariableInputWidget for each variable.

    Manages creation, layout, value retrieval, and validation for
    all variables in a Terraform project.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._widgets: dict[str, VariableInputWidget] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header = QLabel("Variables")
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._header)

        # Scroll area for variable inputs
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.addStretch()

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        # Placeholder shown when no variables
        self._empty_label = QLabel("No project loaded")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: gray; padding: 20px;")
        self._container_layout.insertWidget(0, self._empty_label)

        # Per-variable row height estimate (label + input + margins)
        self._row_height = 40
        self._header_height = 30

    def load_variables(self, variables: list[TerraformVariable],
                       saved_values: Optional[dict] = None):
        """
        Populate the panel with input widgets for the given variables.

        Args:
            variables: List of TerraformVariable from the parser.
            saved_values: Optional dict of previously saved non-sensitive values.
        """
        self.clear()

        if not variables:
            self._empty_label.setText("No variables defined")
            self._empty_label.show()
            self._header.setText("[ Project contains 0 variables ]")
            return

        self._empty_label.hide()
        sensitive_count = sum(1 for v in variables if v.sensitive)
        self._header.setText(
            f"[ Project contains {len(variables)} variables ({sensitive_count} sensitive) ]"
        )

        for var in variables:
            widget = VariableInputWidget(var)
            self._widgets[var.name] = widget
            # Insert before the stretch
            self._container_layout.insertWidget(
                self._container_layout.count() - 1, widget
            )

        # Restore saved values (never for sensitive vars)
        if saved_values:
            for name, value in saved_values.items():
                if name in self._widgets and not self._widgets[name].variable.sensitive:
                    self._widgets[name].set_value(value)

        self._update_max_height()

    def _update_max_height(self):
        """Set maximum height to fit content without excess empty space."""
        count = len(self._widgets)
        if count == 0:
            self.setMaximumHeight(self._header_height + 60)  # placeholder text
        else:
            self.setMaximumHeight(
                self._header_height + (count * self._row_height) + 20
            )

    def clear(self):
        """Remove all variable input widgets."""
        for widget in self._widgets.values():
            self._container_layout.removeWidget(widget)
            widget.deleteLater()
        self._widgets.clear()
        self._empty_label.setText("No project loaded")
        self._empty_label.show()
        self._update_max_height()

    def get_all_values(self) -> dict[str, Any]:
        """Return a dict of variable name -> current value for non-empty fields."""
        values = {}
        for name, widget in self._widgets.items():
            val = widget.get_value()
            if val is not None and val != "":
                values[name] = val
        return values

    def get_var_types(self) -> dict[str, str]:
        """Return a dict of variable name -> type string."""
        return {name: w.variable.type for name, w in self._widgets.items()}

    def get_non_sensitive_values(self) -> dict[str, Any]:
        """Return values for non-sensitive variables only (safe to persist)."""
        values = {}
        for name, widget in self._widgets.items():
            if not widget.variable.sensitive:
                val = widget.get_value()
                if val is not None and val != "":
                    values[name] = val
        return values

    def get_sensitive_names(self) -> set[str]:
        """Return the set of variable names that are marked sensitive."""
        return {name for name, w in self._widgets.items() if w.variable.sensitive}

    def set_values(self, values: dict) -> int:
        """
        Set values on matching variable widgets.

        Args:
            values: Dict of variable name to value.

        Returns:
            Number of variables that were set.
        """
        count = 0
        for name, value in values.items():
            if name in self._widgets:
                self._widgets[name].set_value(value)
                count += 1
        return count

    def all_valid(self) -> bool:
        """Return True if all variable inputs pass validation."""
        return all(w.is_valid() for w in self._widgets.values())
