"""
Polling state tracker for the Renovate PR Assistant.

This module manages polling state information using GitHub Issues as the
storage backend, extending the existing dashboard functionality.
"""

import json
from datetime import datetime
from typing import Any, cast

import structlog

from ..config import Settings
from ..github_client import GitHubClient
from ..issue_manager import IssueStateManager

logger = structlog.get_logger(__name__)


class PollingStateTracker:
    """
    State tracker for polling operations.

    This class extends the existing dashboard functionality to store
    polling-specific metadata and state information.
    """

    def __init__(self, github_client: GitHubClient, settings: Settings):
        """
        Initialize the polling state tracker.

        Args:
            github_client: GitHub API client
            settings: Application settings
        """
        self.github_client = github_client
        self.settings = settings
        self.issue_manager = IssueStateManager(github_client, settings)

    async def get_last_poll_time(self, repo_name: str) -> datetime | None:
        """
        Get the last poll time for a repository.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Last poll timestamp or None if never polled
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            # Extract polling metadata from dashboard issue
            polling_data = await self._extract_polling_data(dashboard_issue)
            last_poll_str = polling_data.get("last_poll_time")

            if last_poll_str:
                return datetime.fromisoformat(last_poll_str.replace("Z", "+00:00"))

            return None

        except Exception as e:
            logger.error(
                "Failed to get last poll time",
                repository=repo_name,
                error=str(e),
            )
            return None

    async def update_last_poll_time(self, repo_name: str, poll_time: datetime) -> bool:
        """
        Update the last poll time for a repository.

        Args:
            repo_name: Full repository name (org/repo)
            poll_time: Timestamp of the poll

        Returns:
            True if successful
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            # Get existing dashboard data
            existing_data = await self._extract_dashboard_data(dashboard_issue)

            # Update polling metadata
            if "polling_metadata" not in existing_data:
                existing_data["polling_metadata"] = {}

            existing_data["polling_metadata"].update(
                {
                    "last_poll_time": poll_time.isoformat(),
                    "last_updated": datetime.now().isoformat(),
                }
            )

            # Update the dashboard issue with new data
            await self._update_dashboard_with_polling_data(
                repo, dashboard_issue, existing_data
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to update last poll time",
                repository=repo_name,
                error=str(e),
            )
            return False

    async def record_polling_metrics(
        self,
        repo_name: str,
        metrics: dict[str, Any],
    ) -> bool:
        """
        Record polling metrics for a repository.

        Args:
            repo_name: Full repository name (org/repo)
            metrics: Polling metrics dictionary

        Returns:
            True if successful
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            # Get existing dashboard data
            existing_data = await self._extract_dashboard_data(dashboard_issue)

            # Update polling metadata
            if "polling_metadata" not in existing_data:
                existing_data["polling_metadata"] = {}

            existing_data["polling_metadata"].update(
                {
                    "metrics": metrics,
                    "metrics_updated": datetime.now().isoformat(),
                }
            )

            # Update the dashboard issue
            await self._update_dashboard_with_polling_data(
                repo, dashboard_issue, existing_data
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to record polling metrics",
                repository=repo_name,
                error=str(e),
            )
            return False

    async def _extract_polling_data(self, dashboard_issue: Any) -> dict[str, Any]:
        """
        Extract polling data from dashboard issue.

        Args:
            dashboard_issue: GitHub issue object

        Returns:
            Polling data dictionary
        """
        try:
            # Parse JSON data from issue body
            dashboard_data = await self._extract_dashboard_data(dashboard_issue)
            return cast(dict[str, Any], dashboard_data.get("polling_metadata", {}))

        except Exception as e:
            logger.error(
                "Failed to extract polling data",
                issue_number=dashboard_issue.number,
                error=str(e),
            )
            return {}

    async def _extract_dashboard_data(self, dashboard_issue: Any) -> dict[str, Any]:
        """
        Extract dashboard data from issue body.

        Args:
            dashboard_issue: GitHub issue object

        Returns:
            Dashboard data dictionary
        """
        try:
            issue_body = dashboard_issue.body or ""

            # Find JSON data block in issue body
            json_start = issue_body.find("```json\n")
            if json_start == -1:
                return {}

            json_start += 8  # Skip "```json\n"
            json_end = issue_body.find("\n```", json_start)
            if json_end == -1:
                return {}

            json_content = issue_body[json_start:json_end]
            return cast(dict[str, Any], json.loads(json_content))

        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                "Failed to parse dashboard data",
                issue_number=dashboard_issue.number,
                error=str(e),
            )
            return {}

    async def _update_dashboard_with_polling_data(
        self,
        repo: Any,
        dashboard_issue: Any,
        updated_data: dict[str, Any],
    ) -> None:
        """
        Update dashboard issue with polling data.

        Args:
            repo: Repository object
            dashboard_issue: Dashboard issue object
            updated_data: Updated dashboard data
        """
        try:
            # Generate updated issue body using the issue manager
            updated_body = await self.issue_manager._generate_dashboard_body(
                updated_data
            )

            # Update the issue
            await self.github_client.update_issue(
                repo=repo,
                issue_number=dashboard_issue.number,
                body=updated_body,
            )

        except Exception as e:
            logger.error(
                "Failed to update dashboard with polling data",
                repository=repo.full_name,
                issue_number=dashboard_issue.number,
                error=str(e),
            )
