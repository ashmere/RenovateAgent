#!/usr/bin/env python3
"""
Standalone application entry point for RenovateAgent.

This module provides the main entry point for running RenovateAgent in
standalone mode, optimized for local development and testing with
polling-based operation.
"""

import asyncio
import logging
import signal
import sys
from typing import Any

from aiohttp import web

from .config import Settings
from .github_client import GitHubClient
from .issue_manager import IssueStateManager
from .polling.orchestrator import PollingOrchestrator
from .pr_processor import PRProcessor
from .state.manager import StateManager, StateManagerFactory
from .telemetry import get_telemetry_manager, initialize_telemetry

logger = logging.getLogger(__name__)


class StandaloneApp:
    """Main application class for standalone mode."""

    def __init__(self) -> None:
        """Initialize the standalone application."""
        self.settings: Settings | None = None
        self.github_client: GitHubClient | None = None
        self.state_manager: StateManager | None = None
        self.pr_processor: PRProcessor | None = None
        self.issue_manager: IssueStateManager | None = None
        self.polling_orchestrator: PollingOrchestrator | None = None
        self._shutdown_event = asyncio.Event()
        self._web_app: web.Application | None = None
        self._web_runner: web.AppRunner | None = None

    async def initialize(self) -> None:
        """Initialize all application components."""
        logger.info("Initializing RenovateAgent in standalone mode...")

        # Load configuration
        try:
            self.settings = Settings()
            logger.info(f"Deployment mode: {self.settings.deployment_mode}")
            logger.info(f"GitHub organization: {self.settings.github_organization}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise

        # Initialize telemetry
        try:
            initialize_telemetry()
            logger.info("OpenTelemetry initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize telemetry: {e}")

        # Validate standalone mode configuration
        if not self.settings.is_standalone_mode:
            raise ValueError(
                f"Application configured for {self.settings.deployment_mode} "
                "mode, but standalone.py requires DEPLOYMENT_MODE=standalone"
            )

        # Initialize GitHub client
        try:
            self.github_client = GitHubClient(self.settings)
            logger.info("GitHub client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize GitHub client: {e}")
            raise

        # Initialize state manager using factory
        try:
            self.state_manager = StateManagerFactory.create_state_manager(
                mode=self.settings.deployment_mode, github_client=self.github_client
            )
            logger.info(
                f"State manager initialized: " f"{type(self.state_manager).__name__}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize state manager: {e}")
            raise

        # Initialize issue manager (for dashboard and legacy compatibility)
        try:
            self.issue_manager = IssueStateManager(
                github_client=self.github_client, settings=self.settings
            )
            logger.info("Issue manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize issue manager: {e}")
            raise

        # Initialize PR processor (for business logic)
        try:
            self.pr_processor = PRProcessor(
                github_client=self.github_client, settings=self.settings
            )
            logger.info("PR processor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PR processor: {e}")
            raise

        # Initialize polling orchestrator (for standalone mode)
        try:
            self.polling_orchestrator = PollingOrchestrator(
                github_client=self.github_client,
                pr_processor=self.pr_processor,
                settings=self.settings,
            )
            logger.info("Polling orchestrator initialized")
        except Exception as e:
            logger.error(f"Failed to initialize polling orchestrator: {e}")
            raise

        logger.info("✅ RenovateAgent standalone mode initialization complete")

    async def start(self) -> None:
        """Start the standalone application."""
        if not self.settings:
            raise RuntimeError("Application not initialized")

        logger.info("Starting RenovateAgent in standalone mode")

        # Start web server for health checks
        await self._start_web_server()

        # Adjust configuration for standalone mode
        if not self.settings.enable_polling:
            logger.info("Enabling polling for standalone mode")
            self.settings.enable_polling = True

        if self.settings.enable_webhooks:
            logger.info("Disabling webhooks for standalone mode")
            self.settings.enable_webhooks = False

        logger.info(
            "Standalone configuration: "
            f"deployment_mode={self.settings.deployment_mode}, "
            f"polling_enabled={self.settings.enable_polling}, "
            f"polling_interval_seconds={self.settings.polling_interval_seconds}, "
            f"max_concurrent_repos={self.settings.polling_concurrent_repos}, "
            f"repositories={len(self.settings.github_repository_allowlist)} configured"
        )

        # Start polling orchestrator
        if self.polling_orchestrator:
            await self.polling_orchestrator.start_polling()
        else:
            raise RuntimeError("Polling orchestrator not initialized")

    async def stop(self) -> None:
        """Stop the standalone application."""
        logger.info("Stopping RenovateAgent...")

        # Stop polling orchestrator
        if self.polling_orchestrator:
            try:
                await self.polling_orchestrator.stop_polling()
                logger.info("Polling orchestrator stopped")
            except Exception as e:
                logger.error(f"Error stopping polling orchestrator: {e}")

        # Stop web server
        await self._stop_web_server()

        # Shutdown telemetry
        try:
            get_telemetry_manager().shutdown()
            logger.info("Telemetry shutdown completed")
        except Exception as e:
            logger.warning(f"Error shutting down telemetry: {e}")

        # Signal shutdown complete
        self._shutdown_event.set()
        logger.info("RenovateAgent stopped")

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame) -> None:  # type: ignore
            logger.info(f"Received signal {signum}, initiating shutdown...")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def health_check(self) -> dict[str, Any]:
        """
        Perform health check of all components.

        Returns:
            Health check results
        """
        health_data: dict[str, Any] = {
            "status": "healthy",
            "mode": "standalone",
            "deployment_mode": (
                self.settings.deployment_mode if self.settings else "unknown"
            ),
            "components": {},
        }

        try:
            # Check GitHub client
            if self.github_client:
                try:
                    # Use the correct method name
                    rate_limit = await self.github_client.get_rate_limit_info()
                    health_data["components"]["github_client"] = "healthy"
                    health_data["rate_limit"] = rate_limit
                except Exception as e:
                    health_data["components"]["github_client"] = f"error: {e}"
                    health_data["status"] = "unhealthy"
            else:
                health_data["components"]["github_client"] = "not_initialized"

            # Check state manager
            if self.state_manager:
                try:
                    stats = self.state_manager.get_memory_stats()
                    health_data["components"]["state_manager"] = {
                        "status": "healthy",
                        "stats": stats,
                    }
                except Exception as e:
                    health_data["components"]["state_manager"] = f"error: {e}"
                    health_data["status"] = "unhealthy"
            else:
                health_data["components"]["state_manager"] = "not_initialized"

            # Check polling orchestrator
            if self.polling_orchestrator:
                health_data["components"]["polling_orchestrator"] = "healthy"
            else:
                health_data["components"]["polling_orchestrator"] = "not_initialized"

        except Exception as e:
            health_data["status"] = "unhealthy"
            health_data["error"] = str(e)

        return health_data

    async def _create_web_app(self) -> web.Application:
        """Create the web application for health checks."""
        app = web.Application()

        async def health_handler(request: web.Request) -> web.Response:
            """Health check endpoint."""
            try:
                health_data = await self.health_check()
                status_code = 200 if health_data["status"] == "healthy" else 503
                return web.json_response(health_data, status=status_code)
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return web.json_response(
                    {"status": "unhealthy", "error": str(e)}, status=503
                )

        app.router.add_get("/health", health_handler)
        return app

    async def _start_web_server(self) -> None:
        """Start the web server for health checks."""
        if not self.settings:
            raise RuntimeError("Settings not initialized")

        self._web_app = await self._create_web_app()
        self._web_runner = web.AppRunner(self._web_app)
        await self._web_runner.setup()

        # Use port 8001 for health checks
        site = web.TCPSite(self._web_runner, "0.0.0.0", 8001)
        await site.start()
        logger.info("Health check server started on http://0.0.0.0:8001")

    async def _stop_web_server(self) -> None:
        """Stop the web server."""
        if self._web_runner:
            await self._web_runner.cleanup()
            logger.info("Health check server stopped")


async def main() -> None:
    """Main entry point for standalone mode."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app = StandaloneApp()

    try:
        # Setup signal handlers
        app.setup_signal_handlers()

        # Initialize application
        await app.initialize()

        # Start application
        await app.start()

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sys.exit(1)
    finally:
        await app.stop()
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
