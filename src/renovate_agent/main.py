"""
Main application entry point for the Renovate PR Assistant.

This module sets up the FastAPI application, configures logging, and starts
the webhook listener service.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

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

    yield

    logger.info("Shutting down Renovate PR Assistant")


# Create FastAPI application
app = FastAPI(
    title="Renovate PR Assistant",
    description="Intelligent automation for Renovate dependency update PRs",
    version="0.1.0",
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
async def root() -> Dict[str, str]:
    """Root endpoint."""
    return {"message": "Renovate PR Assistant", "version": "0.1.0", "status": "active"}


@app.get("/health")
async def health_check() -> Dict[str, str]:
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
