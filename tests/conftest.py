"""
Pytest configuration and fixtures for Renovate PR Assistant tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from renovate_agent.config import Settings
from renovate_agent.github_client import GitHubClient
from renovate_agent.pr_processor import PRProcessor


@pytest.fixture
def mock_settings() -> Settings:
    """Mock settings for testing."""
    return Settings(
        github_app_id=123456,
        github_app_private_key_path="test-key.pem",
        github_webhook_secret="test-secret",
        github_organization="test-org",
        database_url="sqlite:///:memory:",
        debug=True,
        log_level="DEBUG",
    )


@pytest.fixture
def mock_github_client() -> AsyncMock:
    """Mock GitHub client for testing."""
    client = AsyncMock(spec=GitHubClient)
    client.get_repo.return_value = MagicMock()
    client.get_pr.return_value = MagicMock()
    client.approve_pr.return_value = True
    client.get_pr_checks.return_value = []
    return client


@pytest.fixture
def mock_pr_processor(mock_github_client: AsyncMock, mock_settings: Settings) -> PRProcessor:
    """Mock PR processor for testing."""
    return PRProcessor(mock_github_client, mock_settings)


@pytest.fixture
def sample_pr_data() -> Dict[str, Any]:
    """Sample PR data for testing."""
    return {
        "number": 123,
        "title": "Update dependency example to v1.2.3",
        "body": "This PR updates the dependency as requested.",
        "state": "open",
        "user": {
            "login": "renovate[bot]",
            "type": "Bot"
        },
        "head": {
            "ref": "renovate/example-1.2.3",
            "sha": "abc123"
        },
        "base": {
            "ref": "main",
            "repo": {
                "full_name": "test-org/test-repo",
                "clone_url": "https://github.com/test-org/test-repo.git"
            }
        }
    }


@pytest.fixture
def sample_webhook_payload() -> Dict[str, Any]:
    """Sample webhook payload for testing."""
    return {
        "action": "opened",
        "number": 123,
        "pull_request": {
            "number": 123,
            "title": "Update dependency example to v1.2.3",
            "state": "open",
            "user": {
                "login": "renovate[bot]",
                "type": "Bot"
            },
            "head": {
                "ref": "renovate/example-1.2.3",
                "sha": "abc123"
            },
            "base": {
                "ref": "main",
                "repo": {
                    "full_name": "test-org/test-repo"
                }
            }
        },
        "repository": {
            "full_name": "test-org/test-repo",
            "clone_url": "https://github.com/test-org/test-repo.git"
        }
    }


@pytest.fixture
def sample_check_suite() -> Dict[str, Any]:
    """Sample check suite data for testing."""
    return {
        "id": 123456,
        "status": "completed",
        "conclusion": "success",
        "check_runs": [
            {
                "name": "CI",
                "status": "completed",
                "conclusion": "success"
            },
            {
                "name": "Security Scan",
                "status": "completed", 
                "conclusion": "success"
            }
        ]
    }
