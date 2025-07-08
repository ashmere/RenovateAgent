"""
Dependency fixer module for the Renovate PR Assistant.

This module provides language-specific dependency fixing capabilities
for Python (Poetry), TypeScript (npm/yarn), and Go.
"""

from .base import DependencyFixer
from .factory import DependencyFixerFactory
from .go_mod import GoModFixer
from .python_poetry import PythonPoetryFixer
from .typescript_npm import TypeScriptNpmFixer

__all__ = [
    "DependencyFixer",
    "DependencyFixerFactory",
    "PythonPoetryFixer",
    "TypeScriptNpmFixer",
    "GoModFixer",
]
