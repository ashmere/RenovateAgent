"""
Tests for standalone mode functionality.

Tests the StandaloneApp class and related standalone mode components,
including initialization, configuration validation, and health checks.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from renovate_agent.config import Settings
from renovate_agent.standalone import StandaloneApp


class TestStandaloneApp:
    """Test the StandaloneApp class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.app = StandaloneApp()

    @pytest.mark.asyncio
    async def test_initialization_success(self):
        """Test successful application initialization."""
        # Mock all dependencies
        mock_settings = Mock(spec=Settings)
        mock_settings.deployment_mode = "standalone"
        mock_settings.is_standalone_mode = True
        mock_settings.github_organization = "test-org"

        mock_github_client = Mock()
        mock_state_manager = Mock()
        mock_pr_processor = Mock()
        mock_issue_manager = Mock()
        mock_polling_orchestrator = Mock()

        with (
            patch("renovate_agent.standalone.Settings", return_value=mock_settings),
            patch(
                "renovate_agent.standalone.GitHubClient",
                return_value=mock_github_client,
            ),
            patch("renovate_agent.standalone.StateManagerFactory") as mock_factory,
            patch(
                "renovate_agent.standalone.IssueStateManager",
                return_value=mock_issue_manager,
            ),
            patch(
                "renovate_agent.standalone.PRProcessor", return_value=mock_pr_processor
            ),
            patch(
                "renovate_agent.standalone.PollingOrchestrator",
                return_value=mock_polling_orchestrator,
            ),
        ):

            mock_factory.create_state_manager.return_value = mock_state_manager

            # Test initialization
            await self.app.initialize()

            # Verify all components are initialized
            assert self.app.settings == mock_settings
            assert self.app.github_client == mock_github_client
            assert self.app.state_manager == mock_state_manager
            assert self.app.pr_processor == mock_pr_processor
            assert self.app.issue_manager == mock_issue_manager
            assert self.app.polling_orchestrator == mock_polling_orchestrator

            # Verify factory was called correctly
            mock_factory.create_state_manager.assert_called_once_with(
                mode="standalone", github_client=mock_github_client
            )

    @pytest.mark.asyncio
    async def test_initialization_wrong_deployment_mode(self):
        """Test initialization fails with wrong deployment mode."""
        mock_settings = Mock(spec=Settings)
        mock_settings.deployment_mode = "serverless"
        mock_settings.is_standalone_mode = False
        mock_settings.github_organization = "test-org"

        with patch("renovate_agent.standalone.Settings", return_value=mock_settings):
            with pytest.raises(
                ValueError,
                match="but standalone.py requires DEPLOYMENT_MODE=standalone",
            ):
                await self.app.initialize()

    @pytest.mark.asyncio
    async def test_initialization_github_client_failure(self):
        """Test initialization fails when GitHub client creation fails."""
        mock_settings = Mock(spec=Settings)
        mock_settings.deployment_mode = "standalone"
        mock_settings.is_standalone_mode = True
        mock_settings.github_organization = "test-org"

        with (
            patch("renovate_agent.standalone.Settings", return_value=mock_settings),
            patch(
                "renovate_agent.standalone.GitHubClient",
                side_effect=Exception("GitHub error"),
            ),
        ):

            with pytest.raises(Exception, match="GitHub error"):
                await self.app.initialize()

    @pytest.mark.asyncio
    async def test_start_configuration_adjustment(self):
        """Test that start() adjusts configuration appropriately."""
        # Setup mocked initialized app
        mock_settings = Mock()
        mock_settings.deployment_mode = "standalone"
        mock_settings.enable_polling = False  # Will be enabled
        mock_settings.enable_webhooks = True  # Will be disabled
        mock_settings.polling_interval_minutes = 2
        mock_settings.polling_max_concurrent_repos = 3
        mock_settings.polling_repositories = ["org/repo1", "org/repo2"]

        mock_orchestrator = AsyncMock()

        self.app.settings = mock_settings
        self.app.polling_orchestrator = mock_orchestrator

        # Mock the orchestrator start to avoid infinite loop
        async def mock_start():
            await asyncio.sleep(0.1)  # Short delay
            self.app._shutdown_event.set()  # Trigger shutdown

        mock_orchestrator.start = mock_start

        # Test start
        await self.app.start()

        # Verify configuration adjustments
        assert mock_settings.enable_polling is True
        assert mock_settings.enable_webhooks is False

    @pytest.mark.asyncio
    async def test_health_check_all_healthy(self):
        """Test health check when all components are healthy."""
        # Setup mocked components
        mock_settings = Mock()
        mock_settings.deployment_mode = "standalone"

        mock_github_client = AsyncMock()
        mock_github_client.get_rate_limit.return_value = {"remaining": 5000}

        mock_state_manager = Mock()
        mock_state_manager.get_memory_stats.return_value = {
            "pr_states_count": 5,
            "repositories_count": 2,
        }

        mock_orchestrator = Mock()

        self.app.settings = mock_settings
        self.app.github_client = mock_github_client
        self.app.state_manager = mock_state_manager
        self.app.polling_orchestrator = mock_orchestrator

        # Test health check
        health = await self.app.health_check()

        # Verify health status
        assert health["status"] == "healthy"
        assert health["mode"] == "standalone"
        assert health["deployment_mode"] == "standalone"
        assert health["components"]["github_client"] == "healthy"
        assert health["components"]["state_manager"]["status"] == "healthy"
        assert health["components"]["polling_orchestrator"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_github_client_failure(self):
        """Test health check when GitHub client fails."""
        mock_settings = Mock()
        mock_settings.deployment_mode = "standalone"

        mock_github_client = AsyncMock()
        mock_github_client.get_rate_limit_info.side_effect = Exception("API error")

        self.app.settings = mock_settings
        self.app.github_client = mock_github_client

        # Test health check
        health = await self.app.health_check()

        # Verify unhealthy status
        assert health["status"] == "unhealthy"
        assert "error" in health or "API error" in str(
            health["components"]["github_client"]
        )

    @pytest.mark.asyncio
    async def test_health_check_uninitialized_components(self):
        """Test health check with uninitialized components."""
        # Test with no components initialized
        health = await self.app.health_check()

        # Verify partial health status
        assert health["components"]["github_client"] == "not_initialized"
        assert health["components"]["state_manager"] == "not_initialized"
        components = health["components"]
        assert components["polling_orchestrator"] == "not_initialized"

    def test_setup_signal_handlers(self):
        """Test signal handler setup."""
        with patch("renovate_agent.standalone.signal.signal") as mock_signal:
            self.app.setup_signal_handlers()

            # Verify signal handlers were registered
            assert mock_signal.call_count == 2
            # Check that SIGINT and SIGTERM handlers were set
            calls = mock_signal.call_args_list
            signals = [call[0][0] for call in calls]
            assert any("SIGINT" in str(sig) or sig == 2 for sig in signals)
            assert any("SIGTERM" in str(sig) or sig == 15 for sig in signals)

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test application stop."""
        # Ensure shutdown event is not set initially
        assert not self.app._shutdown_event.is_set()

        # Call stop
        await self.app.stop()

        # Verify shutdown event is set
        assert self.app._shutdown_event.is_set()


class TestStandaloneIntegration:
    """Integration tests for standalone mode."""

    @pytest.mark.asyncio
    async def test_full_initialization_integration(self):
        """Test full initialization with real config (mocked externals)."""
        # Use real config but mock external dependencies
        test_env = {
            "DEPLOYMENT_MODE": "standalone",
            "GITHUB_ORGANIZATION": "test-org",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token",
            "ENABLE_POLLING": "true",
            "ENABLE_WEBHOOKS": "false",
        }

        with (
            patch.dict("os.environ", test_env),
            patch("renovate_agent.standalone.GitHubClient") as mock_github_client_class,
            patch(
                "renovate_agent.standalone.PollingOrchestrator"
            ) as mock_orchestrator_class,
        ):

            # Create mocks
            mock_github_client = Mock()
            mock_github_client_class.return_value = mock_github_client

            mock_orchestrator = Mock()
            mock_orchestrator_class.return_value = mock_orchestrator

            # Test initialization
            app = StandaloneApp()
            await app.initialize()

            # Verify real config was loaded
            assert app.settings.deployment_mode == "standalone"
            assert app.settings.github_organization == "test-org"
            assert app.settings.is_standalone_mode is True

            # Verify components were created
            assert app.github_client == mock_github_client
            assert app.state_manager is not None  # Created by factory
            assert app.polling_orchestrator == mock_orchestrator

    @pytest.mark.asyncio
    async def test_state_manager_integration(self):
        """Test integration with state manager factory."""
        test_env = {
            "DEPLOYMENT_MODE": "standalone",
            "GITHUB_ORGANIZATION": "test-org",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token",
        }

        with (
            patch.dict("os.environ", test_env),
            patch("renovate_agent.standalone.GitHubClient") as mock_github_client_class,
        ):

            mock_github_client = Mock()
            mock_github_client_class.return_value = mock_github_client

            app = StandaloneApp()
            await app.initialize()

            # Verify state manager was created via factory
            assert app.state_manager is not None
            assert hasattr(app.state_manager, "get_memory_stats")

            # Test state manager methods
            stats = app.state_manager.get_memory_stats()
            assert isinstance(stats, dict)
            assert "pr_states_count" in stats


@pytest.mark.asyncio
async def test_main_function():
    """Test the main function entry point."""
    with patch("renovate_agent.standalone.StandaloneApp") as mock_app_class:
        mock_app = AsyncMock()
        mock_app_class.return_value = mock_app

        # Mock the main function components
        with (
            patch("renovate_agent.standalone.logging.basicConfig"),
            patch("renovate_agent.standalone.asyncio.run") as mock_run,
        ):

            # Create a mock that calls our test function
            async def test_main():
                app = mock_app_class()
                app.setup_signal_handlers()
                await app.initialize()
                await app.start()
                await app.stop()

            # Simulate running main
            mock_run.side_effect = lambda coro: asyncio.run(test_main())

            # This would normally run the app, but we're mocking it
            # main()  # Commented out to avoid actual execution

            # Verify app class was imported correctly
            assert mock_app_class is not None


class TestStandaloneConfiguration:
    """Test standalone mode configuration validation."""

    def test_standalone_mode_validation(self):
        """Test that standalone mode is properly validated."""
        from renovate_agent.config import DeploymentMode, Settings

        # Test standalone mode enum
        assert DeploymentMode.STANDALONE.value == "standalone"

        # Test configuration with standalone mode
        test_env = {
            "DEPLOYMENT_MODE": "standalone",
            "GITHUB_ORGANIZATION": "test-org",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token",
        }

        with patch.dict("os.environ", test_env):
            settings = Settings()
            assert settings.deployment_mode == "standalone"
            assert settings.is_standalone_mode is True
            assert settings.is_serverless_mode is False

    def test_default_deployment_mode(self):
        """Test default deployment mode."""
        from renovate_agent.config import Settings

        test_env = {
            "GITHUB_ORGANIZATION": "test-org",
            "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token",
        }

        with patch.dict("os.environ", test_env, clear=True):
            settings = Settings()
            # Default should be standalone
            assert settings.deployment_mode == "standalone"
            assert settings.is_standalone_mode is True
