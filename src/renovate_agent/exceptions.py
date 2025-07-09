"""
Custom exceptions for the Renovate PR Assistant.

This module defines custom exception classes for better error handling
and debugging across the application.
"""

from typing import Any


class RenovateAgentError(Exception):
    """Base exception for Renovate PR Assistant errors."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code or "RENOVATE_AGENT_ERROR"
        self.context = context or {}


class GitHubAPIError(RenovateAgentError):
    """Exception for GitHub API related errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message, "GITHUB_API_ERROR", context)
        self.status_code = status_code


class AuthenticationError(RenovateAgentError):
    """Exception for authentication related errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, "AUTHENTICATION_ERROR", context)


class RateLimitError(RenovateAgentError):
    """Exception for rate limit related errors."""

    def __init__(
        self,
        message: str,
        reset_time: float | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message, "RATE_LIMIT_ERROR", context)
        self.reset_time = reset_time


class WebhookValidationError(RenovateAgentError):
    """Exception for webhook validation errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, "WEBHOOK_VALIDATION_ERROR", context)


class DependencyFixingError(RenovateAgentError):
    """Exception for dependency fixing errors."""

    def __init__(
        self,
        message: str,
        language: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message, "DEPENDENCY_FIXING_ERROR", context)
        self.language = language


class ConfigurationError(RenovateAgentError):
    """Exception for configuration related errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, "CONFIGURATION_ERROR", context)


class PRProcessingError(RenovateAgentError):
    """Exception for PR processing errors."""

    def __init__(
        self,
        message: str,
        pr_number: int | None = None,
        repo_name: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message, "PR_PROCESSING_ERROR", context)
        self.pr_number = pr_number
        self.repo_name = repo_name


class IssueStateError(RenovateAgentError):
    """Exception for issue state management errors."""

    def __init__(
        self,
        message: str,
        issue_number: int | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message, "ISSUE_STATE_ERROR", context)
        self.issue_number = issue_number


class DatabaseError(RenovateAgentError):
    """Exception for database related errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message, "DATABASE_ERROR", context)


class ExternalServiceError(RenovateAgentError):
    """Exception for external service errors."""

    def __init__(
        self,
        message: str,
        service: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message, "EXTERNAL_SERVICE_ERROR", context)
        self.service = service
