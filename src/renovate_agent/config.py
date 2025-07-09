"""
Configuration management for the Renovate PR Assistant.

This module handles environment variables, settings validation, and configuration
management using Pydantic Settings for type safety and validation.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubAppConfig(BaseModel):
    """GitHub App configuration settings."""

    app_id: int = Field(..., description="GitHub App ID")
    private_key_path: str = Field(..., description="Path to GitHub App private key")
    webhook_secret: str = Field(..., description="GitHub webhook secret")


class ServerConfig(BaseModel):
    """Web server configuration settings."""

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=False, description="Enable debug mode")


class DatabaseConfig(BaseModel):
    """Database configuration settings."""

    url: str = Field(
        default="sqlite:///./renovate_agent.db", description="Database URL"
    )


class DependencyFixerConfig(BaseModel):
    """Dependency fixer configuration settings."""

    enabled: bool = Field(default=True, description="Enable dependency fixing")
    supported_languages: list[str] = Field(
        default=["python", "typescript", "go"],
        description="List of supported languages",
    )
    clone_timeout: int = Field(default=300, description="Git clone timeout in seconds")
    update_timeout: int = Field(
        default=600, description="Dependency update timeout in seconds"
    )


class PollingConfig(BaseModel):
    """Polling configuration settings."""

    enabled: bool = Field(default=False, description="Enable polling mode")
    base_interval_seconds: int = Field(
        default=120, description="Base polling interval in seconds (2 minutes)"
    )
    max_interval_seconds: int = Field(
        default=600, description="Maximum polling interval in seconds (10 minutes)"
    )
    adaptive_polling: bool = Field(
        default=True, description="Enable adaptive polling frequency"
    )
    activity_window_minutes: int = Field(
        default=30, description="Activity monitoring window in minutes"
    )
    high_activity_threshold: int = Field(
        default=10, description="Active PRs threshold for high activity"
    )
    low_activity_multiplier: float = Field(
        default=3.0, description="Frequency multiplier for low activity"
    )
    api_usage_threshold: float = Field(
        default=0.8, description="API usage threshold to slow down polling"
    )
    rate_limit_check_interval: int = Field(
        default=60, description="Rate limit check interval in seconds"
    )
    error_backoff_seconds: int = Field(
        default=300, description="Error backoff time in seconds"
    )
    max_consecutive_failures: int = Field(
        default=5, description="Maximum consecutive failures before stopping"
    )
    concurrent_repo_polling: int = Field(
        default=5, description="Number of repositories to poll concurrently"
    )


class DashboardConfig(BaseModel):
    """Dashboard configuration settings."""

    issue_title: str = Field(
        default="Renovate PRs Assistant Dashboard",
        description="Title for dashboard issues",
    )
    update_on_events: bool = Field(
        default=True, description="Update dashboard on webhook events"
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # GitHub configuration
    github_app_id: int = Field(default=0, description="GitHub App ID (0 for PAT mode)")
    github_app_private_key_path: str = Field(
        default="", description="GitHub App private key path"
    )
    github_webhook_secret: str = Field(
        default="dev-secret", description="GitHub webhook secret"
    )
    github_personal_access_token: str = Field(
        default="", description="GitHub Personal Access Token (for development)"
    )
    github_api_url: str = Field(
        default="https://api.github.com", description="GitHub API URL"
    )
    github_organization: str = Field(..., description="GitHub organization name")

    # Server configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=False, description="Enable debug mode")

    # Database configuration
    database_url: str = Field(
        default="sqlite:///./renovate_agent.db", description="Database URL"
    )

    # Logging configuration
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format")

    # Dependency fixer configuration
    enable_dependency_fixing: bool = Field(
        default=True, description="Enable dependency fixing"
    )
    supported_languages: str | list[str] = Field(
        default="python,typescript,go",
        description="Supported languages for dependency fixing (comma-separated)",
    )
    clone_timeout: int = Field(default=300, description="Git clone timeout")
    dependency_update_timeout: int = Field(
        default=600, description="Dependency update timeout"
    )

    # Dashboard configuration
    dashboard_issue_title: str = Field(
        default="Renovate PRs Assistant Dashboard", description="Dashboard issue title"
    )
    update_dashboard_on_events: bool = Field(
        default=True, description="Update dashboard on events"
    )
    dashboard_creation_mode: str = Field(
        default="renovate-only",
        description="Dashboard creation mode: test, any, none, renovate-only",
    )

    # Rate limiting
    github_api_rate_limit: int = Field(
        default=5000, description="GitHub API rate limit"
    )
    webhook_rate_limit: int = Field(default=1000, description="Webhook rate limit")

    # Security
    allowed_origins: str | list[str] = Field(
        default="https://github.com",
        description="Allowed CORS origins (comma-separated)",
    )
    enable_cors: bool = Field(default=True, description="Enable CORS")

    # Repository Management
    github_repository_allowlist: str | list[str] = Field(
        default="",
        description="Optional allowlist of repositories to monitor "
        "(comma-separated repo names without org prefix). "
        "If empty, monitors all repos in org.",
    )
    github_test_repositories: str | list[str] = Field(
        default="",
        description="Test repositories for validation and testing "
        "(comma-separated full names with org/repo format)",
    )
    ignore_archived_repositories: bool = Field(
        default=True, description="Ignore archived repositories"
    )

    # Polling Configuration
    enable_polling: bool = Field(default=False, description="Enable polling mode")
    polling_interval_seconds: int = Field(
        default=120, description="Base polling interval in seconds"
    )
    polling_max_interval_seconds: int = Field(
        default=600, description="Maximum polling interval in seconds"
    )
    polling_adaptive: bool = Field(
        default=True, description="Enable adaptive polling frequency"
    )
    polling_concurrent_repos: int = Field(
        default=5, description="Number of repositories to poll concurrently"
    )

    @field_validator("supported_languages", mode="before")
    @classmethod
    def parse_supported_languages(cls, v: Any) -> list[str]:
        """Parse supported languages from comma-separated string or list."""
        if isinstance(v, str):
            # Handle comma-separated string format
            return [lang.strip() for lang in v.split(",") if lang.strip()]
        elif isinstance(v, list):
            # Handle list format (from JSON or direct assignment)
            return v
        else:
            error_msg = f"supported_languages must be a string or list, got {type(v)}"
            raise ValueError(error_msg)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Any) -> list[str]:
        """Parse allowed origins from comma-separated string or list."""
        if isinstance(v, str):
            # Handle comma-separated string format
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            # Handle list format (from JSON or direct assignment)
            return v
        else:
            error_msg = f"allowed_origins must be a string or list, got {type(v)}"
            raise ValueError(error_msg)

    @field_validator("github_repository_allowlist", mode="before")
    @classmethod
    def parse_repository_allowlist(cls, v: Any) -> list[str]:
        """Parse repository allowlist from comma-separated string or list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [repo.strip() for repo in v.split(",") if repo.strip()]
        elif isinstance(v, list):
            return v
        else:
            error_msg = (
                f"github_repository_allowlist must be a string or list, got {type(v)}"
            )
            raise ValueError(error_msg)

    @field_validator("github_test_repositories", mode="before")
    @classmethod
    def parse_test_repositories(cls, v: Any) -> list[str]:
        """Parse test repositories from comma-separated string or list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [repo.strip() for repo in v.split(",") if repo.strip()]
        elif isinstance(v, list):
            return v
        else:
            error_msg = (
                f"github_test_repositories must be a string or list, got {type(v)}"
            )
            raise ValueError(error_msg)

    @field_validator("supported_languages")
    @classmethod
    def validate_supported_languages(cls, v: list[str]) -> list[str]:
        """Validate supported languages list."""
        allowed_languages = {"python", "typescript", "javascript", "go"}
        for lang in v:
            if lang not in allowed_languages:
                raise ValueError(f"Unsupported language: {lang}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()

    @field_validator("dashboard_creation_mode")
    @classmethod
    def validate_dashboard_creation_mode(cls, v: str) -> str:
        """Validate dashboard creation mode."""
        allowed_modes = {"test", "any", "none", "renovate-only"}
        if v not in allowed_modes:
            raise ValueError(f"Invalid dashboard creation mode: {v}")
        return v

    @property
    def github_app_config(self) -> GitHubAppConfig:
        """Get GitHub App configuration."""
        return GitHubAppConfig(
            app_id=self.github_app_id,
            private_key_path=self.github_app_private_key_path,
            webhook_secret=self.github_webhook_secret,
        )

    @property
    def is_development_mode(self) -> bool:
        """Check if running in development mode (using PAT)."""
        return bool(self.github_personal_access_token and self.github_app_id == 0)

    @property
    def server_config(self) -> ServerConfig:
        """Get server configuration."""
        return ServerConfig(host=self.host, port=self.port, debug=self.debug)

    @property
    def database_config(self) -> DatabaseConfig:
        """Get database configuration."""
        return DatabaseConfig(url=self.database_url)

    @property
    def dependency_fixer_config(self) -> DependencyFixerConfig:
        """Get dependency fixer configuration."""
        # Ensure supported_languages is always a list
        supported_langs = self.supported_languages
        if isinstance(supported_langs, str):
            supported_langs = [
                lang.strip() for lang in supported_langs.split(",") if lang.strip()
            ]
        return DependencyFixerConfig(
            enabled=self.enable_dependency_fixing,
            supported_languages=supported_langs,
            clone_timeout=self.clone_timeout,
            update_timeout=self.dependency_update_timeout,
        )

    @property
    def dashboard_config(self) -> DashboardConfig:
        """Get dashboard configuration."""
        return DashboardConfig(
            issue_title=self.dashboard_issue_title,
            update_on_events=self.update_dashboard_on_events,
        )

    @property
    def polling_config(self) -> PollingConfig:
        """Get polling configuration."""
        return PollingConfig(
            enabled=self.enable_polling,
            base_interval_seconds=self.polling_interval_seconds,
            max_interval_seconds=self.polling_max_interval_seconds,
            adaptive_polling=self.polling_adaptive,
            concurrent_repo_polling=self.polling_concurrent_repos,
        )

    def should_process_repository(
        self, repo_name: str, is_archived: bool = False
    ) -> bool:
        """
        Check if a repository should be processed.

        Args:
            repo_name: Repository name (without org prefix)
            is_archived: Whether the repository is archived

        Returns:
            True if repository should be processed
        """
        # Always ignore archived repositories if configured
        if is_archived and self.ignore_archived_repositories:
            return False

        # If no allowlist is set, process all repositories
        if not self.github_repository_allowlist:
            return True

        # Check if repository is in allowlist
        return repo_name in self.github_repository_allowlist

    def get_test_repositories(self) -> list[str]:
        """Get list of test repositories."""
        test_repos = self.github_test_repositories
        if isinstance(test_repos, str):
            if not test_repos.strip():
                return []
            return [repo.strip() for repo in test_repos.split(",") if repo.strip()]
        return test_repos

    def should_create_dashboard(
        self, repository: str, is_renovate_pr: bool = False
    ) -> bool:
        """
        Check if a dashboard should be created based on the creation mode.

        Args:
            repository: Full repository name (org/repo)
            is_renovate_pr: Whether this is a Renovate PR

        Returns:
            True if dashboard should be created
        """
        mode = self.dashboard_creation_mode

        if mode == "none":
            return False
        elif mode == "any":
            return True
        elif mode == "renovate-only":
            return is_renovate_pr
        elif mode == "test":
            test_repos = self.get_test_repositories()
            return repository in test_repos
        else:
            # Default to renovate-only behavior
            return is_renovate_pr


# Global settings instance - initialized lazily to avoid import-time errors
_settings_instance = None


def get_settings() -> Settings:
    """Get the global settings instance, creating it if necessary."""
    global _settings_instance
    if _settings_instance is None:
        try:
            _settings_instance = Settings()  # type: ignore[call-arg,unused-ignore]
        except ValueError as e:
            # If github_organization is not provided, raise a more helpful error
            if "github_organization" in str(e):
                raise ValueError(
                    "GITHUB_ORGANIZATION environment variable is required. "
                    "Please set it to your GitHub organization name."
                ) from e
            raise
    return _settings_instance


# For backward compatibility
def __getattr__(name: str) -> Any:
    """Allow module-level access to settings attributes."""
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
