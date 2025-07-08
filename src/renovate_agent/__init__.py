"""
Renovate PR Assistant

An intelligent automation system for managing Renovate dependency update PRs
across GitHub organizations.
"""

__version__ = "0.1.0"
__author__ = "Renovate PR Assistant"
__email__ = "support@example.com"

from .config import Settings
from .dependency_fixer import DependencyFixerFactory
from .exceptions import RenovateAgentError
from .github_client import GitHubClient
from .pr_processor import PRProcessor
from .webhook_listener import WebhookListener

__all__ = [
    "Settings",
    "GitHubClient",
    "WebhookListener",
    "PRProcessor",
    "RenovateAgentError",
    "DependencyFixerFactory",
]
