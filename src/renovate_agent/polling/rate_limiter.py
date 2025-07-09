"""
Rate limit manager for the Renovate PR Assistant polling system.

This module manages GitHub API rate limits and provides adaptive
throttling for polling operations.
"""

from datetime import datetime, timedelta
from typing import Any

import structlog

from ..config import Settings
from ..github_client import GitHubClient

logger = structlog.get_logger(__name__)


class RateLimitStatus:
    """Rate limit status information."""

    def __init__(
        self,
        remaining: int,
        limit: int,
        reset_time: datetime,
        usage_percentage: float,
        should_slow_down: bool,
    ):
        self.remaining = remaining
        self.limit = limit
        self.reset_time = reset_time
        self.usage_percentage = usage_percentage
        self.should_slow_down = should_slow_down


class RateLimitManager:
    """
    Manager for GitHub API rate limiting.

    This class monitors GitHub API usage and provides recommendations
    for throttling polling operations to stay within limits.
    """

    def __init__(self, github_client: GitHubClient, settings: Settings):
        """
        Initialize the rate limit manager.

        Args:
            github_client: GitHub API client
            settings: Application settings
        """
        self.github_client = github_client
        self.settings = settings
        self.config = settings.polling_config
        self._last_check = None
        self._cached_status = None

    async def check_rate_limits(self) -> RateLimitStatus:
        """
        Check current GitHub API rate limit status.

        Returns:
            Rate limit status information
        """
        now = datetime.now()

        # Use cached status if recent enough
        if (
            self._cached_status
            and self._last_check
            and (now - self._last_check).total_seconds()
            < self.config.rate_limit_check_interval
        ):
            return self._cached_status

        try:
            # Get rate limit from GitHub API
            rate_limit = await self._get_github_rate_limit()

            remaining = rate_limit.get("remaining", 0)
            limit = rate_limit.get("limit", 5000)
            reset_timestamp = rate_limit.get("reset", 0)

            reset_time = datetime.fromtimestamp(reset_timestamp)
            usage_percentage = 1.0 - (remaining / limit) if limit > 0 else 0.0

            threshold = self.config.api_usage_threshold
            should_slow_down = usage_percentage > threshold

            status = RateLimitStatus(
                remaining=remaining,
                limit=limit,
                reset_time=reset_time,
                usage_percentage=usage_percentage,
                should_slow_down=should_slow_down,
            )

            # Cache the status
            self._cached_status = status
            self._last_check = now

            logger.debug(
                "Rate limit status",
                remaining=remaining,
                limit=limit,
                usage_percentage=usage_percentage,
                should_slow_down=should_slow_down,
            )

            return status

        except Exception as e:
            logger.error("Failed to check rate limits", error=str(e))

            # Return conservative default
            return RateLimitStatus(
                remaining=100,
                limit=5000,
                reset_time=now + timedelta(hours=1),
                usage_percentage=0.8,
                should_slow_down=True,
            )

    async def get_current_usage(self) -> int:
        """
        Get current API usage count (approximate).

        Returns:
            Estimated API calls used
        """
        status = await self.check_rate_limits()
        return status.limit - status.remaining

    async def get_remaining_calls(self) -> int:
        """
        Get remaining API calls.

        Returns:
            Remaining API calls
        """
        status = await self.check_rate_limits()
        return status.remaining

    async def calculate_throttle_delay(self) -> float:
        """
        Calculate recommended delay based on rate limit status.

        Returns:
            Recommended delay in seconds
        """
        status = await self.check_rate_limits()

        if not status.should_slow_down:
            return 0.0

        # Calculate delay based on usage percentage
        if status.usage_percentage > 0.9:
            return 60.0  # 1 minute delay for high usage
        elif status.usage_percentage > 0.8:
            return 30.0  # 30 second delay for medium usage
        else:
            return 10.0  # 10 second delay for moderate usage

    async def _get_github_rate_limit(self) -> dict[str, Any]:
        """
        Get rate limit information from GitHub API.

        Returns:
            Rate limit data dictionary
        """
        try:
            # Use GitHub client to get rate limit
            github_instance = self.github_client.get_github_instance()
            rate_limit = github_instance.get_rate_limit()

            # Extract core rate limit (used for most API calls)
            core_limit = rate_limit.core

            return {
                "remaining": core_limit.remaining,
                "limit": core_limit.limit,
                "reset": core_limit.reset.timestamp(),
            }

        except Exception as e:
            logger.error("Failed to get GitHub rate limit", error=str(e))
            raise
