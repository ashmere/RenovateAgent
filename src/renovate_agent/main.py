"""
Main application entry point for the Renovate PR Assistant.

This module sets up the FastAPI application, configures logging, and starts
the webhook listener service.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .github_client import GitHubClient
from .pr_processor import PRProcessor
from .webhook_listener import WebhookListener


def setup_logging() -> None:
    """Configure structured logging."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level), format="%(message)s"
    )

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            (
                structlog.processors.JSONRenderer()
                if settings.log_format == "json"
                else structlog.dev.ConsoleRenderer()
            ),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def _create_startup_dashboards(
    github_client: GitHubClient, logger: structlog.stdlib.BoundLogger
) -> None:
    """Create dashboards on startup if configured to do so."""
    try:
        from .config import get_settings
        from .issue_manager import IssueStateManager

        current_settings = get_settings()

        # Only create dashboards in test mode
        if current_settings.dashboard_creation_mode != "test":
            return

        test_repos = current_settings.get_test_repositories()
        if not test_repos:
            logger.info(
                "No test repositories configured for startup dashboard " "creation"
            )
            return

        logger.info(
            "Creating startup dashboards for test repositories",
            repositories=test_repos,
            mode=current_settings.dashboard_creation_mode,
        )

        issue_manager = IssueStateManager(github_client, current_settings)

        for repo_name in test_repos:
            try:
                repo = await github_client.get_repo(repo_name)
                dashboard_issue = await issue_manager.get_or_create_dashboard_issue(
                    repo
                )

                logger.info(
                    "Startup dashboard ensured",
                    repository=repo_name,
                    issue_number=dashboard_issue.number,
                )

            except Exception as e:
                logger.error(
                    "Failed to create startup dashboard",
                    repository=repo_name,
                    error=str(e),
                )

    except Exception as e:
        logger.error("Failed to create startup dashboards", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    setup_logging()
    logger = structlog.get_logger()

    logger.info("Starting Renovate PR Assistant")
    logger.info(
        "Configuration loaded",
        github_org=settings.github_organization,
        supported_languages=settings.supported_languages,
        debug=settings.debug,
    )

    # Initialize services
    github_client = GitHubClient(settings.github_app_config)
    pr_processor = PRProcessor(github_client, settings)

    # Store services in app state
    app.state.github_client = github_client
    app.state.pr_processor = pr_processor

    # Create startup dashboards if configured
    await _create_startup_dashboards(github_client, logger)

    yield

    logger.info("Shutting down Renovate PR Assistant")


# Create FastAPI application
app = FastAPI(
    title="Renovate PR Assistant",
    description="Intelligent automation for Renovate dependency update PRs",
    version="0.2.0",
    lifespan=lifespan,
)

# Configure CORS
if settings.enable_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

# Include webhook routes
webhook_listener = WebhookListener()
app.include_router(webhook_listener.router, prefix="/webhooks", tags=["webhooks"])


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Renovate PR Assistant", "version": "0.2.0", "status": "active"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


def main() -> None:
    """Main entry point."""
    import uvicorn

    setup_logging()
    logger = structlog.get_logger()

    logger.info(
        "Starting server", host=settings.host, port=settings.port, debug=settings.debug
    )

    uvicorn.run(
        "renovate_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=None,  # We handle logging ourselves
    )


if __name__ == "__main__":
    main()
