"""
Polling orchestrator for the Renovate PR Assistant.

This module manages periodic repository scanning and PR discovery through GitHub API queries.
"""

import asyncio
from datetime import datetime
from typing import Any

import structlog

from ..config import Settings
from ..github_client import GitHubClient
from ..pr_processor import PRProcessor
from .rate_limiter import RateLimitManager
from .state_tracker import PollingStateTracker

logger = structlog.get_logger(__name__)


class RepositoryActivity:
    """Tracks activity metrics for a repository."""

    def __init__(self, repo_name: str):
        self.repo_name = repo_name
        self.last_poll_time: datetime | None = None
        self.last_renovate_pr_count = 0
        self.consecutive_empty_polls = 0
        self.total_polls = 0
        self.total_prs_found = 0
        self.last_activity_detected: datetime | None = None
        self.current_interval_minutes = 2  # Start with default interval
        self.activity_score = 0.0  # 0.0 = inactive, 1.0 = highly active

    def update_after_poll(self, renovate_pr_count: int, poll_time: datetime) -> None:
        """Update activity metrics after a polling cycle."""
        self.last_poll_time = poll_time
        self.total_polls += 1

        if renovate_pr_count > 0:
            self.total_prs_found += renovate_pr_count
            self.consecutive_empty_polls = 0
            self.last_activity_detected = poll_time

            # Increase activity score for new PRs
            if renovate_pr_count > self.last_renovate_pr_count:
                self.activity_score = min(1.0, self.activity_score + 0.3)
        else:
            self.consecutive_empty_polls += 1
            # Decrease activity score for empty polls
            self.activity_score = max(0.0, self.activity_score - 0.1)

        self.last_renovate_pr_count = renovate_pr_count
        self._calculate_optimal_interval()

    def _calculate_optimal_interval(self) -> None:
        """Calculate optimal polling interval based on activity patterns."""
        base_interval = 2  # 2 minutes base
        max_interval = 15  # 15 minutes maximum
        min_interval = 1  # 1 minute minimum

        if self.activity_score >= 0.8:
            # High activity: poll more frequently
            self.current_interval_minutes = min_interval
        elif self.activity_score >= 0.5:
            # Medium activity: standard polling
            self.current_interval_minutes = base_interval
        elif self.activity_score >= 0.2:
            # Low activity: slower polling
            self.current_interval_minutes = min(5, base_interval * 2)
        else:
            # Very low activity: slowest polling
            if self.consecutive_empty_polls >= 5:
                self.current_interval_minutes = min(max_interval, base_interval * 4)
            else:
                self.current_interval_minutes = min(10, base_interval * 3)

    def get_next_poll_delay(self) -> float:
        """Get the delay until next poll in seconds."""
        return self.current_interval_minutes * 60.0

    def should_prioritize(self) -> bool:
        """Check if this repository should be prioritized for polling."""
        return self.activity_score > 0.5 or self.consecutive_empty_polls == 0


class PollingOrchestrator:
    """
    Orchestrates polling operations across multiple repositories.

    This class manages the periodic scanning of repositories for Renovate PRs,
    with intelligent scheduling and rate limiting.
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

        # Initialize components
        self.rate_limiter = RateLimitManager(github_client, settings)
        self.state_tracker = PollingStateTracker(github_client, settings)

        # Polling state
        self.is_running_flag = False
        self.polling_task: asyncio.Task[None] | None = None

        # Repository activity tracking
        self.repository_activities: dict[str, RepositoryActivity] = {}

        # Adaptive polling settings
        self.adaptive_enabled = settings.polling_config.enable_adaptive_intervals
        self.global_backoff_multiplier = 1.0
        self.last_rate_limit_hit: datetime | None = None

    def is_running(self) -> bool:
        """Check if polling is currently active."""
        return self.is_running_flag

    async def start_polling(self) -> None:
        """Start the polling process."""
        if self.is_running_flag:
            logger.warning("Polling already running")
            return

        self.is_running_flag = True
        logger.info(
            "Starting polling orchestrator",
            adaptive_intervals=self.adaptive_enabled,
            default_interval_minutes=self.config.interval_minutes,
            max_concurrent_repos=self.config.max_concurrent_repositories,
        )

        try:
            await self._polling_loop()
        except asyncio.CancelledError:
            logger.info("Polling cancelled")
        except Exception as e:
            logger.error("Polling failed with unexpected error", error=str(e))
        finally:
            self.is_running_flag = False

    async def stop_polling(self) -> None:
        """Stop the polling process."""
        if not self.is_running_flag:
            return

        logger.info("Stopping polling orchestrator")
        self.is_running_flag = False

        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass

    async def _polling_loop(self) -> None:
        """Main polling loop."""
        while self.is_running_flag:
            cycle_start = datetime.now()

            logger.info("Polling cycle started", timestamp=cycle_start.isoformat())

            try:
                # Check rate limits before polling
                rate_status = await self.rate_limiter.check_rate_limits()

                if rate_status.should_slow_down:
                    logger.warning(
                        "Rate limit approaching, applying throttling",
                        usage_percentage=rate_status.usage_percentage,
                        remaining=rate_status.remaining,
                    )

                    # Apply global backoff
                    self.global_backoff_multiplier = min(
                        3.0, self.global_backoff_multiplier * 1.5
                    )
                    self.last_rate_limit_hit = cycle_start
                else:
                    # Gradually reduce backoff when rate limits are healthy
                    if self.global_backoff_multiplier > 1.0:
                        self.global_backoff_multiplier = max(
                            1.0, self.global_backoff_multiplier * 0.9
                        )

                # Get repositories to poll
                repositories = self._get_repositories_for_polling()

                if not repositories:
                    logger.warning("No repositories configured for polling")
                    await asyncio.sleep(self.config.interval_minutes * 60)
                    continue

                # Process repositories with adaptive scheduling
                await self._process_repositories_adaptive(repositories, cycle_start)

                # Calculate next cycle delay
                cycle_duration = (datetime.now() - cycle_start).total_seconds()
                next_cycle_delay = await self._calculate_next_cycle_delay(
                    cycle_duration
                )

                logger.info(
                    "Polling cycle completed",
                    duration_seconds=cycle_duration,
                    repositories_processed=len(repositories),
                    next_cycle_in_seconds=next_cycle_delay,
                )

                # Wait for next cycle
                if self.is_running_flag:
                    await asyncio.sleep(next_cycle_delay)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Error in polling cycle", error=str(e))
                # Wait before retrying
                await asyncio.sleep(60)  # 1 minute error backoff

    async def _process_repositories_adaptive(
        self, repositories: list[str], cycle_start: datetime
    ) -> None:
        """Process repositories with adaptive intervals and prioritization."""

        # Separate repositories by priority if adaptive mode is enabled
        if self.adaptive_enabled:
            priority_repos = []
            regular_repos = []

            for repo_name in repositories:
                activity = self._get_or_create_activity(repo_name)

                # Check if enough time has passed for this repository
                if activity.last_poll_time:
                    time_since_last = (
                        cycle_start - activity.last_poll_time
                    ).total_seconds()
                    required_interval = activity.get_next_poll_delay()

                    if time_since_last < required_interval:
                        continue  # Skip this repository for now

                if activity.should_prioritize():
                    priority_repos.append(repo_name)
                else:
                    regular_repos.append(repo_name)

            # Process priority repositories first
            if priority_repos:
                logger.info(
                    "Processing priority repositories",
                    count=len(priority_repos),
                    repositories=priority_repos,
                )
                await self._process_repository_batch(priority_repos, cycle_start)

            # Process regular repositories
            if regular_repos:
                logger.info(
                    "Processing regular repositories",
                    count=len(regular_repos),
                )
                await self._process_repository_batch(regular_repos, cycle_start)
        else:
            # Process all repositories together in non-adaptive mode
            await self._process_repository_batch(repositories, cycle_start)

    async def _process_repository_batch(
        self, repositories: list[str], cycle_start: datetime
    ) -> None:
        """Process a batch of repositories concurrently."""

        # Limit concurrency
        semaphore = asyncio.Semaphore(self.config.max_concurrent_repositories)

        async def process_single_repo(repo_name: str) -> None:
            async with semaphore:
                await self._process_repository_prs(repo_name, cycle_start)

        # Process repositories concurrently
        tasks = [
            asyncio.create_task(process_single_repo(repo_name))
            for repo_name in repositories
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_repository_prs(
        self, repo_name: str, poll_time: datetime
    ) -> None:
        """Process a single repository for Renovate PRs."""
        try:
            activity = self._get_or_create_activity(repo_name)

            logger.debug(
                "Processing repository",
                repository=repo_name,
                activity_score=activity.activity_score,
                consecutive_empty_polls=activity.consecutive_empty_polls,
            )

            # Get the repository
            repo = await self.github_client.get_repo(repo_name)

            # Get open pull requests
            open_prs = repo.get_pulls(state="open")
            renovate_prs = [
                pr for pr in open_prs if await self.github_client.is_renovate_pr(pr)
            ]

            logger.debug(
                "Found PRs in repository",
                repository=repo_name,
                total_open_prs=len(list(open_prs)),
                renovate_prs=len(renovate_prs),
            )

            # Use delta detection to identify what needs processing
            pr_changes = await self.state_tracker.detect_pr_changes(
                repo_name, renovate_prs
            )

            # Filter to only process new and updated PRs
            prs_to_process = [
                (pr, change_type)
                for pr, change_type in pr_changes
                if change_type in ("new", "updated")
            ]

            logger.info(
                "Delta detection results",
                repository=repo_name,
                total_renovate_prs=len(renovate_prs),
                new_prs=len([c for c in pr_changes if c[1] == "new"]),
                updated_prs=len([c for c in pr_changes if c[1] == "updated"]),
                unchanged_prs=len([c for c in pr_changes if c[1] == "unchanged"]),
                processing_count=len(prs_to_process),
            )

            # Update activity tracking based on total renovate PRs found
            activity.update_after_poll(len(renovate_prs), poll_time)

            # Process each PR that needs processing
            for pr, change_type in prs_to_process:
                if await self._should_process_pr(pr):
                    logger.info(
                        "Processing PR",
                        repository=repo_name,
                        pr_number=pr.number,
                        title=pr.title,
                        change_type=change_type,
                    )

                    # Process the PR using the existing processor
                    await self.pr_processor._process_pr_for_approval(repo, pr)

                    # Mark as processed
                    await self.state_tracker.mark_pr_processed(
                        repo_name, str(pr.number)
                    )

            # Update polling state
            await self.state_tracker.update_last_poll_time(repo_name, poll_time)

        except Exception as e:
            logger.error(
                "Failed to process repository",
                repository=repo_name,
                error=str(e),
            )

            # Update activity to reflect error
            activity = self._get_or_create_activity(repo_name)
            activity.update_after_poll(0, poll_time)

    def _get_or_create_activity(self, repo_name: str) -> RepositoryActivity:
        """Get or create activity tracking for a repository."""
        if repo_name not in self.repository_activities:
            self.repository_activities[repo_name] = RepositoryActivity(repo_name)
        return self.repository_activities[repo_name]

    async def _calculate_next_cycle_delay(self, cycle_duration: float) -> float:
        """Calculate delay until next polling cycle with adaptive logic."""
        if not self.adaptive_enabled:
            # Non-adaptive mode: use fixed interval
            base_delay = self.config.interval_minutes * 60.0
            return (
                max(30.0, base_delay - cycle_duration) * self.global_backoff_multiplier
            )

        # Adaptive mode: calculate based on repository activities
        if not self.repository_activities:
            return self.config.interval_minutes * 60.0 * self.global_backoff_multiplier

        # Find the shortest interval among active repositories
        min_interval = float("inf")
        for activity in self.repository_activities.values():
            if activity.last_poll_time:
                next_poll_delay = activity.get_next_poll_delay()
                time_since_last = (
                    datetime.now() - activity.last_poll_time
                ).total_seconds()
                remaining_delay = max(0, next_poll_delay - time_since_last)
                min_interval = min(min_interval, remaining_delay)

        if min_interval == float("inf"):
            min_interval = self.config.interval_minutes * 60.0

        # Apply global backoff and ensure minimum delay
        final_delay = max(30.0, min_interval) * self.global_backoff_multiplier

        logger.debug(
            "Calculated next cycle delay",
            min_interval=min_interval,
            global_backoff=self.global_backoff_multiplier,
            final_delay=final_delay,
        )

        return final_delay

    def _get_repositories_for_polling(self) -> list[str]:
        """Get list of repositories to poll."""
        # Use repository allowlist if configured
        allowlist = self.settings.github_repository_allowlist
        if allowlist:
            # Ensure it's always a list
            if isinstance(allowlist, str):
                repos = [repo.strip() for repo in allowlist.split(",") if repo.strip()]
                return repos
            return allowlist

        # Fall back to test repositories
        test_repos = self.settings.get_test_repositories()
        if test_repos:
            return test_repos

        logger.warning("No repositories configured for polling")
        return []

    async def _should_process_pr(self, pr: Any) -> bool:
        """Check if a PR should be processed."""
        try:
            # Check if already processed
            is_processed = await self.state_tracker.is_pr_processed(
                pr.base.repo.full_name, str(pr.number)
            )

            if is_processed:
                logger.debug(
                    "PR already processed, skipping",
                    repository=pr.base.repo.full_name,
                    pr_number=pr.number,
                )
                return False

            # Basic checks
            if pr.state != "open":
                return False

            if pr.draft:
                logger.debug(
                    "Skipping draft PR",
                    repository=pr.base.repo.full_name,
                    pr_number=pr.number,
                )
                return False

            return True

        except Exception as e:
            logger.error(
                "Error checking if PR should be processed",
                pr_number=pr.number,
                error=str(e),
            )
            return False

    def get_activity_summary(self) -> dict[str, Any]:
        """Get summary of repository activities for monitoring."""
        if not self.repository_activities:
            return {}

        summary = {}
        for repo_name, activity in self.repository_activities.items():
            summary[repo_name] = {
                "activity_score": activity.activity_score,
                "current_interval_minutes": activity.current_interval_minutes,
                "consecutive_empty_polls": activity.consecutive_empty_polls,
                "total_polls": activity.total_polls,
                "total_prs_found": activity.total_prs_found,
                "last_poll": (
                    activity.last_poll_time.isoformat()
                    if activity.last_poll_time
                    else None
                ),
                "last_activity": (
                    activity.last_activity_detected.isoformat()
                    if activity.last_activity_detected
                    else None
                ),
            }

        return summary
