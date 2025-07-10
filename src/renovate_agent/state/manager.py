"""
State management abstraction for RenovateAgent.

Provides pluggable state backends for different deployment modes:
- Serverless: In-memory state with GitHub API fallback
- Standalone: In-memory state with optional Redis persistence
"""

import logging
import sys
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..github_client import GitHubClient

logger = logging.getLogger(__name__)


class StateManager(ABC):
    """Abstract base class for state management."""

    @abstractmethod
    async def get_pr_state(self, repo: str, pr_number: int) -> dict[str, Any] | None:
        """
        Get PR state by repository and PR number.

        Args:
            repo: Repository name (e.g., 'owner/repo')
            pr_number: Pull request number

        Returns:
            PR state dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set_pr_state(
        self, repo: str, pr_number: int, state: dict[str, Any]
    ) -> None:
        """
        Set PR state for a repository and PR number.

        Args:
            repo: Repository name (e.g., 'owner/repo')
            pr_number: Pull request number
            state: State dictionary to store
        """
        pass

    @abstractmethod
    async def get_repository_metadata(self, repo: str) -> dict[str, Any] | None:
        """
        Get repository metadata.

        Args:
            repo: Repository name (e.g., 'owner/repo')

        Returns:
            Repository metadata dictionary or None if not found
        """
        pass

    @abstractmethod
    async def set_repository_metadata(
        self, repo: str, metadata: dict[str, Any]
    ) -> None:
        """
        Set repository metadata.

        Args:
            repo: Repository name (e.g., 'owner/repo')
            metadata: Metadata dictionary to store
        """
        pass

    @abstractmethod
    async def get_all_repositories(self) -> list[str]:
        """
        Get list of all repositories with state.

        Returns:
            List of repository names
        """
        pass

    @abstractmethod
    async def get_repository_prs(self, repo: str) -> list[dict[str, Any]]:
        """
        Get all PRs for a repository.

        Args:
            repo: Repository name (e.g., 'owner/repo')

        Returns:
            List of PR state dictionaries
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the state backend is healthy.

        Returns:
            True if healthy, False otherwise
        """
        pass

    @abstractmethod
    async def clear_repository_state(self, repo: str) -> None:
        """
        Clear all state for a repository.

        Args:
            repo: Repository name (e.g., 'owner/repo')
        """
        pass

    def get_memory_stats(self) -> dict[str, Any]:
        """Get memory usage statistics."""
        return {
            "pr_states_count": 0,
            "repositories_count": 0,
            "memory_usage_bytes": 0,
        }


class InMemoryStateManager(StateManager):
    """In-memory state management for both serverless and standalone modes."""

    def __init__(self, github_client: Optional["GitHubClient"] = None) -> None:
        """Initialize in-memory state manager."""
        self.pr_states: dict[str, dict[str, Any]] = {}
        self.repo_metadata: dict[str, dict[str, Any]] = {}
        self.github_client = github_client
        self._last_cleanup = datetime.now(UTC)

    async def get_pr_state(self, repo: str, pr_number: int) -> dict[str, Any] | None:
        """Get PR state from memory, with optional GitHub API fallback."""
        key = f"{repo}#{pr_number}"
        state = self.pr_states.get(key)

        if not state and self.github_client:
            logger.debug(
                f"PR state not found in memory for {key}, attempting rebuild from GitHub"
            )
            state = await self._rebuild_from_github(repo, pr_number)
            if state:
                self.pr_states[key] = state
                logger.debug(f"Rebuilt PR state for {key} from GitHub API")

        return state

    async def set_pr_state(
        self, repo: str, pr_number: int, state: dict[str, Any]
    ) -> None:
        """Set PR state in memory."""
        key = f"{repo}#{pr_number}"

        # Add metadata
        state = state.copy()  # Don't mutate the original
        state.update(
            {
                "repo": repo,
                "pr_number": pr_number,
                "last_updated": datetime.now(UTC).isoformat(),
            }
        )

        self.pr_states[key] = state
        logger.debug(f"Set PR state for {key}")

    async def get_repository_metadata(self, repo: str) -> dict[str, Any] | None:
        """Get repository metadata from memory."""
        return self.repo_metadata.get(repo)

    async def set_repository_metadata(
        self, repo: str, metadata: dict[str, Any]
    ) -> None:
        """Set repository metadata in memory."""
        metadata = metadata.copy()  # Don't mutate the original
        metadata.update(
            {
                "repo": repo,
                "last_updated": datetime.now(UTC).isoformat(),
            }
        )

        self.repo_metadata[repo] = metadata
        logger.debug(f"Set repository metadata for {repo}")

    async def get_all_repositories(self) -> list[str]:
        """Get list of all repositories with state."""
        # Combine repos from PR states and metadata
        repos_from_prs = {key.split("#")[0] for key in self.pr_states.keys()}
        repos_from_metadata = set(self.repo_metadata.keys())
        all_repos = repos_from_prs | repos_from_metadata
        return sorted(all_repos)

    async def get_repository_prs(self, repo: str) -> list[dict[str, Any]]:
        """Get all PRs for a repository."""
        prs = []
        for key, state in self.pr_states.items():
            if key.startswith(f"{repo}#"):
                prs.append(state)

        # Sort by PR number
        prs.sort(key=lambda x: x.get("pr_number", 0))
        return prs

    async def health_check(self) -> bool:
        """Check if in-memory state is healthy (always true for memory)."""
        return True

    async def clear_repository_state(self, repo: str) -> None:
        """Clear all state for a repository."""
        # Clear PR states
        keys_to_remove = [
            key for key in self.pr_states.keys() if key.startswith(f"{repo}#")
        ]
        for key in keys_to_remove:
            del self.pr_states[key]

        # Clear repository metadata
        if repo in self.repo_metadata:
            del self.repo_metadata[repo]

        logger.info(f"Cleared all state for repository {repo}")

    async def _rebuild_from_github(
        self, repo: str, pr_number: int
    ) -> dict[str, Any] | None:
        """
        Rebuild state from GitHub API - acceptable cost trade-off for serverless.

        This method makes 1-3 API calls to rebuild PR state when not found in memory.
        For serverless mode, this is an acceptable trade-off vs infrastructure costs.
        """
        if not self.github_client:
            return None

        try:
            logger.debug(f"Rebuilding state for {repo}#{pr_number} from GitHub API")

            # Get PR data from GitHub
            pr_data = await self.github_client.get_pr(repo, pr_number)
            if not pr_data:
                logger.warning(f"PR {repo}#{pr_number} not found on GitHub")
                return None

            # Build basic state from PR data
            state = {
                "repo": repo,
                "pr_number": pr_number,
                "title": pr_data.get("title", ""),
                "state": pr_data.get("state", ""),
                "sha": pr_data.get("head", {}).get("sha", ""),
                "updated_at": pr_data.get("updated_at", ""),
                "mergeable": pr_data.get("mergeable"),
                "mergeable_state": pr_data.get("mergeable_state", ""),
                "base_sha": pr_data.get("base", {}).get("sha", ""),
                "last_processed": None,  # Not processed yet
                "processing_status": "discovered",
                "rebuilding_from_github": True,
                "rebuilt_at": datetime.now(UTC).isoformat(),
            }

            logger.info(
                f"Successfully rebuilt state for {repo}#{pr_number} from GitHub API"
            )
            return state

        except Exception as e:
            logger.error(
                f"Failed to rebuild state for {repo}#{pr_number} from GitHub: {e}"
            )
            return None

    def get_memory_stats(self) -> dict[str, Any]:
        """Get memory usage statistics."""
        pr_states_count = len(self.pr_states)
        repositories_count = len(
            {pr_state.get("repository", "") for pr_state in self.pr_states.values()}
        )

        return {
            "pr_states_count": pr_states_count,
            "repositories_count": repositories_count,
            "memory_usage_bytes": (
                sys.getsizeof(self.pr_states) + sys.getsizeof(self.repo_metadata)
            ),
        }

    def _estimate_memory_size(self) -> int:
        """Estimate memory usage in bytes (rough approximation)."""
        import sys

        total_size = 0
        total_size += sys.getsizeof(self.pr_states)
        for key, value in self.pr_states.items():
            total_size += sys.getsizeof(key) + sys.getsizeof(value)

        total_size += sys.getsizeof(self.repo_metadata)
        for key, value in self.repo_metadata.items():
            total_size += sys.getsizeof(key) + sys.getsizeof(value)

        return total_size


class StateManagerFactory:
    """Factory for creating appropriate state manager based on deployment mode."""

    @staticmethod
    def create_state_manager(
        mode: str, github_client: Optional["GitHubClient"] = None, **kwargs: Any
    ) -> StateManager:
        """
        Create state manager instance based on deployment mode.

        Args:
            mode: Deployment mode ('serverless' or 'standalone')
            github_client: Optional GitHub client for fallback operations
            **kwargs: Additional configuration options

        Returns:
            StateManager instance

        Raises:
            ValueError: If mode is not supported
        """
        mode = mode.lower()

        if mode == "serverless":
            logger.info("Creating in-memory state manager for serverless mode")
            return InMemoryStateManager(github_client=github_client)
        elif mode == "standalone":
            logger.info("Creating in-memory state manager for standalone mode")
            # For local development, same in-memory approach
            # Could optionally use Redis if configured in kwargs
            redis_url = kwargs.get("redis_url")
            if redis_url:
                logger.info(
                    f"Redis URL provided: {redis_url}, but Redis implementation not yet available"
                )
                logger.info("Falling back to in-memory state manager")

            return InMemoryStateManager(github_client=github_client)
        else:
            raise ValueError(
                f"Unknown deployment mode: {mode}. Supported modes: 'serverless', 'standalone'"
            )

    @staticmethod
    def get_supported_modes() -> list[str]:
        """Get list of supported deployment modes."""
        return ["serverless", "standalone"]
