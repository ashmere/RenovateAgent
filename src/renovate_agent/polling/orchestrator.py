"""
Polling orchestrator for the Renovate PR Assistant.

This module implements the main polling loop that periodically checks
repositories for changes and processes them using existing PR logic.
"""

import asyncio
import time
from datetime import datetime
from typing import Any

import structlog

from ..config import Settings
from ..github_client import GitHubClient
from ..pr_processor import PRProcessor
from .rate_limiter import RateLimitManager
from .state_tracker import PollingStateTracker

logger = structlog.get_logger(__name__)


class PollingResult:
    """Result of a single polling cycle."""

    def __init__(
        self,
        repository: str,
        changes_detected: int,
        api_calls_used: int,
        poll_duration: float,
        errors: list[str] | None = None,
    ):
        self.repository = repository
        self.changes_detected = changes_detected
        self.api_calls_used = api_calls_used
        self.poll_duration = poll_duration
        self.errors = errors or []
        self.timestamp = datetime.now()


class PollingOrchestrator:
    """
    Main polling orchestrator for repository monitoring.

    This class manages the polling loop, coordinates state tracking, and
    processes detected changes using the existing PR processing logic.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        pr_processor: PRProcessor,
        settings: Settings,
    ):
        """
        Initialize the polling orchestrator.

        Args:
            github_client: GitHub API client
            pr_processor: PR processing engine
            settings: Application settings
        """
        self.github_client = github_client
        self.pr_processor = pr_processor
        self.settings = settings
        self.config = settings.polling_config
        self.state_tracker = PollingStateTracker(github_client, settings)
        self.rate_limiter = RateLimitManager(github_client, settings)

        self._running = False
        self._consecutive_failures = 0
        self._repositories: list[str] = []

    async def start_polling(self) -> None:
        """Start the main polling loop."""
        if self._running:
            logger.warning("Polling is already running")
            return

        if not self.config.enabled:
            logger.info("Polling is disabled in configuration")
            return

        logger.info(
            "Starting polling orchestrator",
            interval_seconds=self.config.base_interval_seconds,
            adaptive_polling=self.config.adaptive_polling,
        )

        self._running = True
        self._consecutive_failures = 0

        # Initialize repositories list
        await self._refresh_repositories()

        try:
            while self._running:
                cycle_start = time.time()

                try:
                    await self._poll_cycle()
                    self._consecutive_failures = 0

                except Exception as e:
                    self._consecutive_failures += 1
                    logger.error(
                        "Polling cycle failed",
                        error=str(e),
                        consecutive_failures=self._consecutive_failures,
                    )

                    max_failures = self.config.max_consecutive_failures
                    if self._consecutive_failures >= max_failures:
                        logger.error(
                            "Maximum consecutive failures reached, stopping polling",
                            max_failures=max_failures,
                        )
                        break

                # Calculate next interval and sleep
                if self._running:  # Check if still running after potential stop
                    interval = await self._calculate_next_interval()
                    cycle_duration = time.time() - cycle_start
                    sleep_time = max(0, interval - cycle_duration)

                    logger.debug(
                        "Polling cycle completed",
                        cycle_duration_seconds=cycle_duration,
                        next_interval_seconds=sleep_time,
                        repositories_checked=len(self._repositories),
                    )

                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)

        finally:
            self._running = False
            logger.info("Polling orchestrator stopped")

    async def stop_polling(self) -> None:
        """Stop the polling loop."""
        logger.info("Stopping polling orchestrator")
        self._running = False

    def is_running(self) -> bool:
        """Check if polling is currently running."""
        return self._running

    async def _poll_cycle(self) -> None:
        """Execute a single polling cycle."""
        if not self._repositories:
            await self._refresh_repositories()

        if not self._repositories:
            logger.warning("No repositories to monitor")
            return

        # Check rate limits before proceeding
        rate_limit_status = await self.rate_limiter.check_rate_limits()
        if rate_limit_status.should_slow_down:
            logger.warning(
                "Rate limit threshold reached, slowing down",
                usage_percentage=rate_limit_status.usage_percentage,
            )

        # Poll repositories with concurrency control
        semaphore = asyncio.Semaphore(self.config.concurrent_repo_polling)
        tasks = [
            self._poll_repository_with_semaphore(semaphore, repo)
            for repo in self._repositories
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        total_changes = 0
        total_errors = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Repository polling failed",
                    repository=self._repositories[i],
                    error=str(result),
                )
                total_errors += 1
            elif isinstance(result, PollingResult):
                total_changes += result.changes_detected
                if result.errors:
                    total_errors += len(result.errors)

        logger.info(
            "Polling cycle summary",
            repositories_polled=len(self._repositories),
            total_changes_detected=total_changes,
            total_errors=total_errors,
        )

    async def _poll_repository_with_semaphore(
        self, semaphore: asyncio.Semaphore, repo_name: str
    ) -> PollingResult:
        """Poll a single repository with concurrency control."""
        async with semaphore:
            return await self._poll_repository(repo_name)

    async def _poll_repository(self, repo_name: str) -> PollingResult:
        """
        Poll a single repository for changes.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Polling result
        """
        start_time = time.time()
        changes_detected = 0
        errors = []
        api_calls_start = await self.rate_limiter.get_current_usage()

        try:
            logger.debug("Polling repository", repository=repo_name)

            # Get repository object
            repo = await self.github_client.get_repo(repo_name)

            # Check if repository should be processed
            if not self.github_client.should_process_repository(repo):
                return PollingResult(
                    repository=repo_name,
                    changes_detected=0,
                    api_calls_used=0,
                    poll_duration=time.time() - start_time,
                )

            # Get last poll time for this repository
            last_poll = await self.state_tracker.get_last_poll_time(repo_name)

            # Get PRs updated since last poll
            prs = await self._get_updated_prs(repo, last_poll)

            for pr_data in prs:
                try:
                    # Check if this is a Renovate PR
                    pr = await self.github_client.get_pr(repo, pr_data["number"])
                    if await self.github_client.is_renovate_pr(pr):
                        # Process the PR using existing logic
                        await self._process_discovered_pr(repo, pr_data)
                        changes_detected += 1

                except Exception as e:
                    error_msg = f"Failed to process PR {pr_data['number']}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg, repository=repo_name)

            # Update last poll time
            await self.state_tracker.update_last_poll_time(repo_name, datetime.now())

        except Exception as e:
            error_msg = f"Repository polling failed: {e}"
            errors.append(error_msg)
            logger.error(error_msg, repository=repo_name)

        api_calls_end = await self.rate_limiter.get_current_usage()
        api_calls_used = max(0, api_calls_end - api_calls_start)

        return PollingResult(
            repository=repo_name,
            changes_detected=changes_detected,
            api_calls_used=api_calls_used,
            poll_duration=time.time() - start_time,
            errors=errors,
        )

    async def _get_updated_prs(
        self, repo: Any, since: datetime | None
    ) -> list[dict[str, Any]]:
        """
        Get PRs updated since the last poll.

        Args:
            repo: Repository object
            since: Last poll timestamp

        Returns:
            List of PR data dictionaries
        """
        # For the basic implementation, get all open PRs
        # In the future, we can optimize this with GitHub API filters
        try:
            # Get all open pull requests
            pulls = repo.get_pulls(state="open", sort="updated", direction="desc")

            pr_list = []
            for pr in pulls:
                # Convert to dict format similar to webhook data
                pr_dict = {
                    "number": pr.number,
                    "title": pr.title,
                    "updated_at": pr.updated_at,
                    "state": pr.state,
                    "user": {"login": pr.user.login},
                    "head": {"sha": pr.head.sha},
                }

                # If we have a since timestamp, filter by update time
                if since is None or pr.updated_at > since:
                    pr_list.append(pr_dict)

            return pr_list

        except Exception as e:
            logger.error(
                "Failed to get updated PRs",
                repository=repo.full_name,
                error=str(e),
            )
            return []

    async def _process_discovered_pr(self, repo: Any, pr_data: dict[str, Any]) -> None:
        """
        Process a discovered PR using existing processing logic.

        Args:
            repo: Repository object
            pr_data: PR data dictionary
        """
        try:
            # Use existing PR processor logic
            result = await self.pr_processor.process_pr_event(
                action="opened",  # Treat discovered PRs as "opened" events
                pr_data=pr_data,
                repo_data={"full_name": repo.full_name},
            )

            logger.info(
                "Processed discovered PR",
                repository=repo.full_name,
                pr_number=pr_data["number"],
                result=result.get("message", "unknown"),
            )

        except Exception as e:
            logger.error(
                "Failed to process discovered PR",
                repository=repo.full_name,
                pr_number=pr_data["number"],
                error=str(e),
            )

    async def _refresh_repositories(self) -> None:
        """Refresh the list of repositories to monitor."""
        try:
            org_repos = await self.github_client.get_organization_repositories(
                self.settings.github_organization
            )

            # Filter repositories based on configuration
            filtered_repos = []
            for repo in org_repos:
                if self.settings.should_process_repository(repo.name, repo.archived):
                    filtered_repos.append(repo.full_name)

            self._repositories = filtered_repos

            logger.info(
                "Refreshed repository list",
                total_repositories=len(filtered_repos),
                organization=self.settings.github_organization,
            )

        except Exception as e:
            logger.error(
                "Failed to refresh repository list",
                organization=self.settings.github_organization,
                error=str(e),
            )

    async def _calculate_next_interval(self) -> int:
        """
        Calculate the next polling interval.

        Returns:
            Next interval in seconds
        """
        if not self.config.adaptive_polling:
            return self.config.base_interval_seconds

        # For basic implementation, return base interval
        # Advanced adaptive logic will be implemented in Phase 2
        return self.config.base_interval_seconds
