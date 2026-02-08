"""
Default settings for TerryGUI.

These are the default values used when no user configuration exists.
"""

DEFAULT_SETTINGS = {
    "version": "1.0.0",
    
    # Recent projects
    "recent_projects": [],
    "max_recent_projects": 10,
    "last_project_path": "",
    
    # Editor configuration
    "editor_command": "code",
    
    # Terraform binary
    "terraform_binary": "terraform",
    
    # UI preferences
    "default_debug_output": False,
    
    # Window settings
    "window": {
        "width": 900,
        "height": 700,
        "maximized": False,
        "x": None,  # None means center on screen
        "y": None,
    },
    
    # Output viewer settings
    "output_viewer": {
        "font_family": "monospace",
        "font_size": 10,
        "max_lines": 10000,
        "auto_scroll": True,
    },
    
    # Confirmation dialogs
    "confirmations": {
        "apply": True,
        "destroy": True,
        "workspace_delete": True,
    },
}
