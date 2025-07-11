"""
Serverless entry point for RenovateAgent using functions-framework.

This module provides a Cloud Function entry point that processes GitHub
webhooks using the existing RenovateAgent processing pipeline.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import time
from typing import Any

import functions_framework
from flask import Request

from renovate_agent.config import get_settings
from renovate_agent.github_client import GitHubClient
from renovate_agent.pr_processor import PRProcessor

# Configure simple logging for serverless
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Global instances (reused across invocations for cost optimization)
_github_client: GitHubClient | None = None
_pr_processor: PRProcessor | None = None
_settings = None


def _get_processor() -> PRProcessor:
    """Get or create processor instance (reused across invocations)."""
    global _github_client, _pr_processor, _settings

    if _pr_processor is None:
        _settings = get_settings()

        # Ensure serverless mode
        if _settings.deployment_mode != "serverless":
            logger.warning("Forcing serverless mode in Cloud Function")
            _settings.deployment_mode = "serverless"

        _github_client = GitHubClient(_settings)
        _pr_processor = PRProcessor(_github_client, _settings)

        logger.info(
            "Initialized serverless processor: %s, org: %s",
            _settings.deployment_mode,
            _settings.github_organization,
        )

    return _pr_processor


def _validate_github_signature(payload: bytes, signature: str) -> bool:
    """Validate GitHub webhook signature."""
    webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.warning("No webhook secret configured - skipping validation")
        return True  # Allow for development/testing

    if not signature:
        logger.warning("No GitHub signature provided")
        return False

    try:
        expected_signature = (
            "sha256="
            + hmac.new(
                webhook_secret.encode("utf-8"), payload, hashlib.sha256
            ).hexdigest()
        )

        is_valid = hmac.compare_digest(signature, expected_signature)
        logger.info(f"GitHub signature validation result: {is_valid}")
        return is_valid

    except Exception as e:
        logger.error(f"Error validating GitHub signature: {str(e)}")
        return False


def _extract_webhook_info(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract useful information from GitHub webhook payload."""
    try:
        info = {"action": payload.get("action"), "event_type": "unknown"}

        # Extract PR information if available
        if "pull_request" in payload:
            pr = payload["pull_request"]
            info.update(
                {
                    "event_type": "pull_request",
                    "pr_number": pr.get("number"),
                    "pr_title": pr.get("title"),
                    "pr_user": pr.get("user", {}).get("login"),
                    "pr_branch": pr.get("head", {}).get("ref"),
                    "pr_state": pr.get("state"),
                }
            )

        # Extract repository information
        if "repository" in payload:
            repo = payload["repository"]
            info.update(
                {
                    "repository": repo.get("full_name"),
                    "repo_owner": repo.get("owner", {}).get("login"),
                    "repo_name": repo.get("name"),
                }
            )

        return info

    except Exception as e:
        logger.error(f"Error extracting webhook info: {str(e)}")
        return {"event_type": "unknown", "action": "unknown"}


async def _process_webhook_async(payload: dict[str, Any]) -> dict[str, Any]:
    """Process webhook asynchronously."""
    try:
        processor = _get_processor()

        # Extract webhook information for logging
        webhook_info = _extract_webhook_info(payload)

        logger.info(
            f"Processing webhook: {webhook_info['event_type']} "
            f"action={webhook_info['action']} "
            f"repo={webhook_info.get('repository')} "
            f"pr={webhook_info.get('pr_number')}"
        )

        # Process the webhook using existing logic
        if webhook_info["event_type"] == "pull_request":
            pr_number = webhook_info.get("pr_number")
            repo_name = webhook_info.get("repository")

            if pr_number and repo_name:
                # Process the PR using existing logic
                result = await processor.process_pr_webhook(
                    repo_name, pr_number, payload
                )
                return result
            else:
                logger.warning("Missing PR number or repository name")
                return {"success": False, "message": "Missing required webhook data"}
        else:
            logger.info(f"Ignoring non-PR webhook event: {webhook_info['event_type']}")
            return {"success": True, "message": "Event ignored", "processed": False}

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return {"success": False, "message": str(e)}


@functions_framework.http  # type: ignore[misc]
def renovate_webhook(request: Request) -> tuple[dict[str, Any], int]:
    """
    Cloud Function entry point for GitHub webhooks.

    This function processes GitHub webhook events and routes them to the
    appropriate RenovateAgent processing pipeline.

    Args:
        request: Flask request object containing webhook payload

    Returns:
        Tuple of (response_dict, status_code)
    """
    start_time = time.time()

    try:
        # Handle health check requests
        health_paths = ["/health", "/healthz", "/"]
        if request.method == "GET" and request.path in health_paths:
            try:
                settings = get_settings()
                return {
                    "status": "healthy",
                    "deployment_mode": settings.deployment_mode,
                    "version": "0.7.0",
                    "timestamp": time.time(),
                }, 200
            except Exception as e:
                logger.error("Health check failed: %s", str(e))
                return {"status": "unhealthy", "error": str(e)}, 500

        # Validate request method for webhook processing
        if request.method != "POST":
            return {"error": "Method not allowed"}, 405

        # Get webhook payload
        try:
            payload = request.get_json()
        except Exception as e:
            logger.error(f"Error parsing JSON payload: {str(e)}")
            return {"error": "Invalid JSON payload"}, 400

        if not payload:
            return {"error": "Empty payload"}, 400

        # Validate GitHub signature
        signature = request.headers.get("X-Hub-Signature-256")
        if not _validate_github_signature(request.data, signature):
            return {"error": "Invalid signature"}, 401

        # Process webhook asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(_process_webhook_async(payload))
        finally:
            loop.close()

        execution_time = time.time() - start_time

        # Log successful processing
        logger.info(
            "Webhook processed successfully in %.2fs: success=%s processed=%s",
            execution_time,
            result.get("success", False),
            result.get("processed", False),
        )

        return {
            "status": "success",
            "success": result.get("success", False),
            "processed": result.get("processed", False),
            "message": result.get("message", "OK"),
            "execution_time": execution_time,
        }, 200

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(
            f"Error processing webhook after {execution_time:.2f}s: {str(e)}",
            exc_info=True,
        )
        return {"error": "Internal server error"}, 500


if __name__ == "__main__":
    # For local testing
    print("Starting RenovateAgent serverless function locally...")
    print("Use 'functions-framework --target=renovate_webhook --port=8090' to run")
