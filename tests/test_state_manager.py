"""
Tests for the state management system.

Tests both the abstract StateManager interface and the InMemoryStateManager implementation,
including deployment mode considerations and GitHub API fallback functionality.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from renovate_agent.state.manager import (
    InMemoryStateManager,
    StateManager,
    StateManagerFactory,
)


class TestInMemoryStateManager:
    """Test the InMemoryStateManager implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.github_client = Mock()
        self.github_client.get_pr = AsyncMock()
        self.state_manager = InMemoryStateManager(github_client=self.github_client)

    @pytest.mark.asyncio
    async def test_pr_state_storage_and_retrieval(self):
        """Test basic PR state storage and retrieval."""
        repo = "test-org/test-repo"
        pr_number = 123
        state = {
            "title": "Test PR",
            "state": "open",
            "sha": "abc123",
            "processing_status": "pending",
        }

        # Store state
        await self.state_manager.set_pr_state(repo, pr_number, state)

        # Retrieve state
        retrieved_state = await self.state_manager.get_pr_state(repo, pr_number)

        # Verify state was stored and enhanced with metadata
        assert retrieved_state is not None
        assert retrieved_state["title"] == "Test PR"
        assert retrieved_state["state"] == "open"
        assert retrieved_state["sha"] == "abc123"
        assert retrieved_state["repo"] == repo
        assert retrieved_state["pr_number"] == pr_number
        assert "last_updated" in retrieved_state

    @pytest.mark.asyncio
    async def test_pr_state_not_found_returns_none(self):
        """Test that missing PR state returns None when no GitHub client."""
        state_manager = InMemoryStateManager(github_client=None)

        result = await state_manager.get_pr_state("test-org/test-repo", 999)

        assert result is None

    @pytest.mark.asyncio
    async def test_pr_state_github_fallback_success(self):
        """Test GitHub API fallback when PR state not found in memory."""
        repo = "test-org/test-repo"
        pr_number = 456

        # Mock GitHub API response
        github_pr_data = {
            "title": "GitHub PR Title",
            "state": "open",
            "head": {"sha": "github-sha-123"},
            "base": {"sha": "base-sha-456"},
            "updated_at": "2024-01-15T10:00:00Z",
            "mergeable": True,
            "mergeable_state": "clean",
        }
        self.github_client.get_pr.return_value = github_pr_data

        # Retrieve state (should trigger GitHub fallback)
        retrieved_state = await self.state_manager.get_pr_state(repo, pr_number)

        # Verify GitHub client was called
        self.github_client.get_pr.assert_called_once_with(repo, pr_number)

        # Verify state was built from GitHub data
        assert retrieved_state is not None
        assert retrieved_state["title"] == "GitHub PR Title"
        assert retrieved_state["state"] == "open"
        assert retrieved_state["sha"] == "github-sha-123"
        assert retrieved_state["base_sha"] == "base-sha-456"
        assert retrieved_state["rebuilding_from_github"] is True
        assert "rebuilt_at" in retrieved_state

    @pytest.mark.asyncio
    async def test_pr_state_github_fallback_failure(self):
        """Test GitHub API fallback when PR not found on GitHub."""
        repo = "test-org/test-repo"
        pr_number = 999

        # Mock GitHub API to return None (PR not found)
        self.github_client.get_pr.return_value = None

        # Retrieve state (should trigger GitHub fallback)
        retrieved_state = await self.state_manager.get_pr_state(repo, pr_number)

        # Verify GitHub client was called
        self.github_client.get_pr.assert_called_once_with(repo, pr_number)

        # Verify None is returned when GitHub doesn't have the PR
        assert retrieved_state is None

    @pytest.mark.asyncio
    async def test_pr_state_github_fallback_exception(self):
        """Test GitHub API fallback when GitHub client raises exception."""
        repo = "test-org/test-repo"
        pr_number = 789

        # Mock GitHub API to raise exception
        self.github_client.get_pr.side_effect = Exception("API Error")

        # Retrieve state (should trigger GitHub fallback and handle exception)
        retrieved_state = await self.state_manager.get_pr_state(repo, pr_number)

        # Verify GitHub client was called
        self.github_client.get_pr.assert_called_once_with(repo, pr_number)

        # Verify None is returned when GitHub API fails
        assert retrieved_state is None

    @pytest.mark.asyncio
    async def test_repository_metadata_storage_and_retrieval(self):
        """Test repository metadata storage and retrieval."""
        repo = "test-org/test-repo"
        metadata = {"default_branch": "main", "language": "python", "private": False}

        # Store metadata
        await self.state_manager.set_repository_metadata(repo, metadata)

        # Retrieve metadata
        retrieved_metadata = await self.state_manager.get_repository_metadata(repo)

        # Verify metadata was stored and enhanced
        assert retrieved_metadata is not None
        assert retrieved_metadata["default_branch"] == "main"
        assert retrieved_metadata["language"] == "python"
        assert retrieved_metadata["repo"] == repo
        assert "last_updated" in retrieved_metadata

    @pytest.mark.asyncio
    async def test_repository_metadata_not_found_returns_none(self):
        """Test that missing repository metadata returns None."""
        result = await self.state_manager.get_repository_metadata("nonexistent/repo")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_repositories(self):
        """Test getting all repositories with state."""
        # Add PR states for multiple repositories
        await self.state_manager.set_pr_state("org/repo1", 1, {"title": "PR 1"})
        await self.state_manager.set_pr_state("org/repo1", 2, {"title": "PR 2"})
        await self.state_manager.set_pr_state("org/repo2", 1, {"title": "PR 3"})

        # Add repository metadata
        await self.state_manager.set_repository_metadata("org/repo3", {"lang": "go"})

        # Get all repositories
        repositories = await self.state_manager.get_all_repositories()

        # Verify all repositories are returned and sorted
        assert len(repositories) == 3
        assert "org/repo1" in repositories
        assert "org/repo2" in repositories
        assert "org/repo3" in repositories
        assert repositories == sorted(repositories)  # Should be sorted

    @pytest.mark.asyncio
    async def test_get_repository_prs(self):
        """Test getting all PRs for a specific repository."""
        repo = "test-org/test-repo"

        # Add multiple PRs for the repository
        await self.state_manager.set_pr_state(repo, 3, {"title": "PR 3"})
        await self.state_manager.set_pr_state(repo, 1, {"title": "PR 1"})
        await self.state_manager.set_pr_state(repo, 2, {"title": "PR 2"})

        # Add PR for different repository (should be excluded)
        await self.state_manager.set_pr_state(
            "other-org/other-repo", 1, {"title": "Other PR"}
        )

        # Get PRs for the specific repository
        prs = await self.state_manager.get_repository_prs(repo)

        # Verify PRs are returned and sorted by PR number
        assert len(prs) == 3
        assert prs[0]["pr_number"] == 1
        assert prs[1]["pr_number"] == 2
        assert prs[2]["pr_number"] == 3
        assert all(pr["repo"] == repo for pr in prs)

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check always returns True for in-memory."""
        result = await self.state_manager.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_clear_repository_state(self):
        """Test clearing all state for a repository."""
        repo = "test-org/test-repo"
        other_repo = "test-org/other-repo"

        # Add state for multiple repositories
        await self.state_manager.set_pr_state(repo, 1, {"title": "PR 1"})
        await self.state_manager.set_pr_state(repo, 2, {"title": "PR 2"})
        await self.state_manager.set_pr_state(other_repo, 1, {"title": "Other PR"})
        await self.state_manager.set_repository_metadata(repo, {"lang": "python"})
        await self.state_manager.set_repository_metadata(other_repo, {"lang": "go"})

        # Clear state for one repository
        await self.state_manager.clear_repository_state(repo)

        # Verify only the specified repository state was cleared
        assert await self.state_manager.get_pr_state(repo, 1) is None
        assert await self.state_manager.get_pr_state(repo, 2) is None
        assert await self.state_manager.get_repository_metadata(repo) is None

        # Verify other repository state remains
        assert await self.state_manager.get_pr_state(other_repo, 1) is not None
        assert await self.state_manager.get_repository_metadata(other_repo) is not None

    async def test_get_memory_stats(self):
        """Test memory statistics collection."""
        # Add some test data
        await self.state_manager.set_pr_state(
            "test-repo", 123, {"status": "open", "repository": "test-repo"}
        )
        await self.state_manager.set_repository_metadata(
            "test-repo", {"last_scan": "2024-01-01"}
        )

        # Get stats
        stats = self.state_manager.get_memory_stats()

        # Verify structure
        assert "pr_states_count" in stats
        assert "repositories_count" in stats
        assert "memory_usage_bytes" in stats

        # Verify data
        assert stats["pr_states_count"] == 1
        assert stats["repositories_count"] == 1
        assert stats["memory_usage_bytes"] > 0

    @pytest.mark.asyncio
    async def test_state_immutability(self):
        """Test that original state objects are not mutated."""
        original_state = {"title": "Original Title", "status": "open"}
        original_copy = original_state.copy()

        # Store state (should not mutate original)
        await self.state_manager.set_pr_state("org/repo", 1, original_state)

        # Verify original state is unchanged
        assert original_state == original_copy
        assert "last_updated" not in original_state
        assert "repo" not in original_state


class TestStateManagerFactory:
    """Test the StateManagerFactory."""

    def test_create_serverless_state_manager(self):
        """Test creating state manager for serverless mode."""
        github_client = Mock()

        state_manager = StateManagerFactory.create_state_manager(
            "serverless", github_client=github_client
        )

        assert isinstance(state_manager, InMemoryStateManager)
        assert state_manager.github_client is github_client

    def test_create_standalone_state_manager(self):
        """Test creating state manager for standalone mode."""
        github_client = Mock()

        state_manager = StateManagerFactory.create_state_manager(
            "standalone", github_client=github_client
        )

        assert isinstance(state_manager, InMemoryStateManager)
        assert state_manager.github_client is github_client

    def test_create_standalone_with_redis_url(self):
        """Test creating standalone state manager with Redis URL (falls back to memory)."""
        github_client = Mock()

        with patch("renovate_agent.state.manager.logger") as mock_logger:
            state_manager = StateManagerFactory.create_state_manager(
                "standalone",
                github_client=github_client,
                redis_url="redis://localhost:6379",
            )

            # Should still create InMemoryStateManager (Redis not implemented yet)
            assert isinstance(state_manager, InMemoryStateManager)

            # Should log that Redis is not available
            mock_logger.info.assert_any_call(
                "Redis URL provided: redis://localhost:6379, but Redis implementation not yet available"
            )

    def test_create_state_manager_case_insensitive(self):
        """Test that mode parameter is case insensitive."""
        github_client = Mock()

        state_manager = StateManagerFactory.create_state_manager(
            "SERVERLESS", github_client=github_client
        )

        assert isinstance(state_manager, InMemoryStateManager)

    def test_create_state_manager_invalid_mode(self):
        """Test creating state manager with invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Unknown deployment mode: invalid"):
            StateManagerFactory.create_state_manager("invalid")

    def test_get_supported_modes(self):
        """Test getting list of supported modes."""
        modes = StateManagerFactory.get_supported_modes()

        assert "serverless" in modes
        assert "standalone" in modes
        assert len(modes) == 2


class TestStateManagerInterface:
    """Test the abstract StateManager interface."""

    def test_state_manager_is_abstract(self):
        """Test that StateManager cannot be instantiated directly."""
        with pytest.raises(TypeError):
            StateManager()

    def test_state_manager_methods_are_abstract(self):
        """Test that all required methods are marked as abstract."""
        # This is more of a documentation test to ensure interface completeness
        abstract_methods = StateManager.__abstractmethods__

        expected_methods = {
            "get_pr_state",
            "set_pr_state",
            "get_repository_metadata",
            "set_repository_metadata",
            "get_all_repositories",
            "get_repository_prs",
            "health_check",
            "clear_repository_state",
        }

        assert abstract_methods == expected_methods
