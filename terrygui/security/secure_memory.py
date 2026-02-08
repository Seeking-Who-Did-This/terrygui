"""
Secure memory handling for sensitive data.

This module provides utilities for handling sensitive data in memory:
- SecureString: Container for sensitive strings with automatic cleanup
- OutputRedactor: Redacts sensitive values from output text
"""

from typing import List, Optional


class SecureString:
    """
    Container for sensitive strings with automatic memory cleanup.
    
    Security features:
    - Value stored privately
    - Automatic zeroing on deletion
    - No string representation (prevents accidental logging)
    - Context manager support
    
    Example:
        >>> password = SecureString("my_secret_password")
        >>> actual_value = password.get_value()
        >>> # Use actual_value...
        >>> password.clear()  # Explicit cleanup
    """
    
    def __init__(self, value: str):
        """
        Initialize with sensitive value.
        
        Args:
            value: The sensitive string to protect
        """
        self._value: Optional[str] = value
        self._cleared = False
    
    def __del__(self):
        """Automatically clear value when object is destroyed."""
        self.clear()
    
    def __str__(self) -> str:
        """Return redacted representation."""
        return "[REDACTED]"
    
    def __repr__(self) -> str:
        """Return redacted representation."""
        return "SecureString([REDACTED])"
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clear on exit."""
        self.clear()
        return False
    
    def get_value(self) -> str:
        """
        Get the actual sensitive value.
        
        Use this method sparingly and only when absolutely necessary.
        Clear the returned value from memory when done.
        
        Returns:
            The sensitive string value
            
        Raises:
            ValueError: If value has been cleared
        """
        if self._cleared or self._value is None:
            raise ValueError("SecureString value has been cleared")
        return self._value
    
    def clear(self):
        """
        Explicitly clear the sensitive value from memory.
        
        After calling this, get_value() will raise ValueError.
        This method is idempotent (safe to call multiple times).
        """
        if not self._cleared and self._value is not None:
            # Attempt to overwrite memory (Python limitation: may not work due to string interning)
            # This is defense-in-depth, not a guarantee
            try:
                self._value = '\x00' * len(self._value)
            except:
                pass  # Best effort
            finally:
                self._value = None
                self._cleared = True
    
    def is_cleared(self) -> bool:
        """
        Check if value has been cleared.
        
        Returns:
            True if cleared, False otherwise
        """
        return self._cleared


class OutputRedactor:
    """
    Redacts sensitive values from text output.
    
    Use this to sanitize terraform output before displaying to user,
    ensuring sensitive variable values are never shown.
    
    Example:
        >>> secrets = {"api_key": SecureString("secret123")}
        >>> redactor = OutputRedactor(secrets)
        >>> output = "Connecting with key: secret123"
        >>> safe_output = redactor.redact(output)
        >>> print(safe_output)
        Connecting with key: [REDACTED]
    """
    
    def __init__(self, sensitive_variables: dict = None):
        """
        Initialize redactor with sensitive values.
        
        Args:
            sensitive_variables: Dict mapping variable names to SecureString values
        """
        self.sensitive_values: List[str] = []
        
        if sensitive_variables:
            self.add_sensitive_values(sensitive_variables)
    
    def add_sensitive_values(self, sensitive_variables: dict):
        """
        Add sensitive values to redaction list.
        
        Args:
            sensitive_variables: Dict mapping variable names to SecureString values
        """
        for var_name, secure_str in sensitive_variables.items():
            if isinstance(secure_str, SecureString):
                try:
                    value = secure_str.get_value()
                    if value and len(value) > 0:
                        self.sensitive_values.append(value)
                except ValueError:
                    # Value already cleared, skip
                    pass
    
    def redact(self, text: str) -> str:
        """
        Replace any occurrence of sensitive values with [REDACTED].
        
        Security note:
        - Uses exact string matching (not regex) to avoid ReDoS attacks
        - Case-sensitive matching
        - Replaces all occurrences
        
        Args:
            text: Text to redact
            
        Returns:
            Text with sensitive values replaced by [REDACTED]
        """
        if not text:
            return text
        
        redacted = text
        
        for sensitive_value in self.sensitive_values:
            if not sensitive_value:
                continue
            
            # Simple string replacement (not regex, to avoid ReDoS)
            redacted = redacted.replace(sensitive_value, "[REDACTED]")
        
        return redacted
    
    def clear(self):
        """
        Clear all sensitive values from memory.
        
        Call this when done with the redactor to ensure cleanup.
        """
        # Attempt to overwrite sensitive values in memory
        for i in range(len(self.sensitive_values)):
            try:
                self.sensitive_values[i] = '\x00' * len(self.sensitive_values[i])
            except:
                pass
        
        self.sensitive_values.clear()
