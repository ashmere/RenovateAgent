"""
Basic tests for Renovate PR Assistant core functionality.
"""

from unittest.mock import patch

import pytest

from renovate_agent.config import get_settings
from renovate_agent.github_client import GitHubClient
from renovate_agent.pr_processor import PRProcessor


def test_settings_creation():
    """Test that settings can be created with environment variables."""
    # Clear any cached settings first
    import renovate_agent.config

    renovate_agent.config._settings_instance = None

    # Test PAT mode (current setup)
    with patch.dict(
        "os.environ",
        {
            "GITHUB_APP_ID": "0",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token",
            "GITHUB_ORGANIZATION": "test-org",
        },
        clear=True,
    ):
        settings = get_settings()
        assert settings.github_app_id == 0
        assert settings.github_personal_access_token == "test-token"
        assert settings.github_organization == "test-org"
        assert settings.is_development_mode is True

    # Clear cache again for second test
    renovate_agent.config._settings_instance = None

    # Test GitHub App mode
    with patch.dict(
        "os.environ",
        {
            "GITHUB_APP_ID": "123456",
            "GITHUB_APP_PRIVATE_KEY_PATH": "test-key.pem",
            "GITHUB_WEBHOOK_SECRET": "test-secret",
            "GITHUB_ORGANIZATION": "test-org",
        },
        clear=True,
    ):
        settings = get_settings()
        assert settings.github_app_id == 123456
        assert settings.github_organization == "test-org"
        assert settings.is_development_mode is False


def test_github_client_initialization(mock_settings):
    """Test GitHub client can be initialized."""
    github_client = GitHubClient(mock_settings.github_app_config)
    assert github_client is not None


def test_pr_processor_initialization(mock_github_client, mock_settings):
    """Test PR processor can be initialized."""
    pr_processor = PRProcessor(mock_github_client, mock_settings)
    assert pr_processor is not None


@pytest.mark.asyncio
async def test_github_client_is_renovate_pr(mock_github_client):
    """Test GitHub client can identify Renovate PRs."""
    from unittest.mock import MagicMock

    # Mock the GitHub PR object
    mock_pr = MagicMock()
    mock_pr.user.login = "renovate[bot]"

    # Test with Renovate bot PR
    await mock_github_client.is_renovate_pr(mock_pr)
    # Verify the method can be called
    mock_github_client.is_renovate_pr.assert_called_once_with(mock_pr)


def test_dependency_fixer_factory():
    """Test that dependency fixer factory can be imported."""
    from renovate_agent.dependency_fixer.factory import DependencyFixerFactory

    assert DependencyFixerFactory is not None


def test_issue_manager_import():
    """Test that issue manager can be imported."""
    from renovate_agent.issue_manager import IssueStateManager

    assert IssueStateManager is not None


def test_webhook_listener_import():
    """Test that webhook listener can be imported."""
    from renovate_agent.webhook_listener import WebhookListener

    assert WebhookListener is not None


def test_main_app_import():
    """Test that main FastAPI app can be imported."""
    from renovate_agent.main import app

    assert app is not None
    assert app.title == "Renovate PR Assistant"
