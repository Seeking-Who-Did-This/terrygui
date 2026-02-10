"""
TerryGUI - A professional Qt-based GUI for managing Terraform projects.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="terrygui",
    version="0.9.0",
    author="TerryGUI Contributors",
    description="A professional Qt-based GUI for managing Terraform projects",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Seeking-Who-Did-This/terrygui",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "PySide6>=6.4.0",
        "python-hcl2>=4.3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-qt>=4.2.0",
            "black>=22.0.0",
            "mypy>=0.990",
        ],
    },
    entry_points={
        "gui_scripts": [
            "terrygui=terrygui.main:main",
        ],
    },
)
