"""
Tests for deployment mode configuration.

Tests the DeploymentMode enum and related configuration functionality
added to support serverless vs standalone deployment modes.
"""

import os
from unittest.mock import patch

import pytest

from renovate_agent.config import DeploymentMode, Settings


class TestDeploymentMode:
    """Test the DeploymentMode enum."""

    def test_deployment_mode_values(self):
        """Test that DeploymentMode has correct values."""
        assert DeploymentMode.SERVERLESS.value == "serverless"
        assert DeploymentMode.STANDALONE.value == "standalone"

    def test_deployment_mode_string_conversion(self):
        """Test that DeploymentMode can be created from strings."""
        assert DeploymentMode("serverless") == DeploymentMode.SERVERLESS
        assert DeploymentMode("standalone") == DeploymentMode.STANDALONE

    def test_deployment_mode_invalid_value(self):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError):
            DeploymentMode("invalid")


class TestSettingsDeploymentMode:
    """Test deployment mode integration in Settings."""

    def test_default_deployment_mode(self):
        """Test that default deployment mode is standalone."""
        with patch.dict(os.environ, {"GITHUB_ORGANIZATION": "test-org"}, clear=True):
            settings = Settings()
            assert settings.deployment_mode == "standalone"

    def test_deployment_mode_from_env(self):
        """Test setting deployment mode from environment variable."""
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "serverless", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()
            assert settings.deployment_mode == "serverless"

    def test_deployment_mode_validation_valid(self):
        """Test that valid deployment modes pass validation."""
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "serverless", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()
            assert settings.deployment_mode == "serverless"

        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "standalone", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()
            assert settings.deployment_mode == "standalone"

    def test_deployment_mode_validation_invalid(self):
        """Test that invalid deployment modes raise validation error."""
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "invalid", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            with pytest.raises(ValueError, match="Invalid deployment mode: invalid"):
                Settings()

    def test_deployment_mode_enum_property(self):
        """Test the deployment_mode_enum property."""
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "serverless", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()
            assert settings.deployment_mode_enum == DeploymentMode.SERVERLESS

        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "standalone", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()
            assert settings.deployment_mode_enum == DeploymentMode.STANDALONE

    def test_is_serverless_mode_property(self):
        """Test the is_serverless_mode property."""
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "serverless", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()
            assert settings.is_serverless_mode is True
            assert settings.is_standalone_mode is False

    def test_is_standalone_mode_property(self):
        """Test the is_standalone_mode property."""
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "standalone", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()
            assert settings.is_standalone_mode is True
            assert settings.is_serverless_mode is False

    def test_deployment_mode_case_insensitive_in_validation(self):
        """Test that deployment mode validation handles case differences."""
        # The validation should catch this since enum creation is case sensitive
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "SERVERLESS", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            with pytest.raises(ValueError, match="Invalid deployment mode: SERVERLESS"):
                Settings()

    def test_deployment_mode_integration_with_existing_config(self):
        """Test that deployment mode works with existing configuration."""
        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_MODE": "serverless",
                "GITHUB_ORGANIZATION": "test-org",
                "GITHUB_PERSONAL_ACCESS_TOKEN": "test-token",
                "DEBUG": "true",
            },
            clear=True,
        ):
            settings = Settings()

            # Verify deployment mode works
            assert settings.is_serverless_mode is True

            # Verify existing config still works
            assert settings.github_organization == "test-org"
            assert settings.github_personal_access_token == "test-token"
            assert settings.debug is True


class TestDeploymentModeIntegration:
    """Test integration between deployment mode and other systems."""

    def test_serverless_mode_implications(self):
        """Test configuration implications for serverless mode."""
        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "serverless", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()

            assert settings.is_serverless_mode is True

            # Serverless typically implies webhooks, not polling
            # (These are separate settings but often correlate)
            # We're not enforcing this at the config level yet

            # Verify other properties still work
            assert settings.github_organization == "test-org"

    def test_standalone_mode_implications(self):
        """Test configuration implications for standalone mode."""
        with patch.dict(
            os.environ,
            {
                "DEPLOYMENT_MODE": "standalone",
                "GITHUB_ORGANIZATION": "test-org",
                "ENABLE_POLLING": "true",
            },
            clear=True,
        ):
            settings = Settings()

            assert settings.is_standalone_mode is True

            # Standalone typically implies polling for local dev
            assert settings.enable_polling is True

            # Verify other properties still work
            assert settings.github_organization == "test-org"

    def test_deployment_mode_with_state_manager_factory(self):
        """Test that deployment mode can be used with StateManagerFactory."""
        from renovate_agent.state.manager import StateManagerFactory

        with patch.dict(
            os.environ,
            {"DEPLOYMENT_MODE": "serverless", "GITHUB_ORGANIZATION": "test-org"},
            clear=True,
        ):
            settings = Settings()

            # Should be able to create state manager with this mode
            state_manager = StateManagerFactory.create_state_manager(
                settings.deployment_mode
            )

            # Verify state manager was created successfully
            assert state_manager is not None
            from renovate_agent.state.manager import InMemoryStateManager

            assert isinstance(state_manager, InMemoryStateManager)
