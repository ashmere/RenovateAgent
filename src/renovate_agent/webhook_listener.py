"""
GitHub webhook listener for the Renovate PR Assistant.

This module handles incoming GitHub webhook events, validates signatures,
and routes events to appropriate processors.
"""

import hashlib
import hmac
import json
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import settings
from .github_client import GitHubClient
from .pr_processor import PRProcessor

logger = structlog.get_logger(__name__)


class WebhookListener:
    """
    GitHub webhook listener and event processor.

    This class handles incoming GitHub webhook events, validates signatures,
    and routes events to appropriate processors.
    """

    def __init__(self) -> None:
        """Initialize the webhook listener."""
        self.router = APIRouter()
        self._setup_routes()
        self.supported_events = {"pull_request", "check_suite", "issues", "push"}

    def _setup_routes(self) -> None:
        """Set up webhook routes."""
        self.router.post("/github")(self.handle_github_webhook)
        self.router.get("/github")(self.webhook_info)

    def _validate_signature(self, payload: bytes, signature: str) -> bool:
        """
        Validate GitHub webhook signature.

        Args:
            payload: Raw webhook payload
            signature: GitHub signature header

        Returns:
            True if signature is valid
        """
        # Skip signature validation in development mode
        from .config import get_settings

        current_settings = get_settings()
        if (
            hasattr(current_settings, "is_development_mode")
            and current_settings.is_development_mode
        ):
            logger.info("Development mode: skipping webhook signature validation")
            return True

        if not signature:
            return False

        expected_signature = hmac.new(
            settings.github_webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

        expected_signature = f"sha256={expected_signature}"

        return hmac.compare_digest(expected_signature, signature)

    def _get_pr_processor(self) -> PRProcessor:
        """Get PR processor instance."""
        from .config import get_settings

        current_settings = get_settings()
        github_client = GitHubClient(current_settings)
        return PRProcessor(github_client, current_settings)

    async def handle_github_webhook(
        self,
        request: Request,
        x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
        x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
        x_github_delivery: str | None = Header(None, alias="X-GitHub-Delivery"),
        user_agent: str | None = Header(None, alias="User-Agent"),
    ) -> JSONResponse:
        """
        Handle incoming GitHub webhook events.

        Args:
            request: FastAPI request object
            x_github_event: GitHub event type
            x_hub_signature_256: GitHub signature
            x_github_delivery: GitHub delivery ID
            user_agent: User agent header

        Returns:
            JSON response
        """
        # Get raw payload
        payload = await request.body()

        # Validate signature
        if not x_hub_signature_256 or not self._validate_signature(
            payload, x_hub_signature_256
        ):
            logger.error(
                "Invalid webhook signature",
                webhook_event_type=x_github_event,
                delivery_id=x_github_delivery,
            )
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse JSON payload
        try:
            data = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(
                "Invalid JSON payload",
                webhook_event_type=x_github_event,
                delivery_id=x_github_delivery,
                error=str(e),
            )
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

        # Log webhook event
        logger.info(
            "Received GitHub webhook",
            webhook_event_type=x_github_event,
            action=data.get("action"),
            delivery_id=x_github_delivery,
            repository=data.get("repository", {}).get("full_name"),
        )

        # Check if event is supported
        if x_github_event not in self.supported_events:
            logger.info(
                "Unsupported event type, ignoring", webhook_event_type=x_github_event
            )
            return JSONResponse(
                content={"message": "Event not supported"}, status_code=200
            )

        # Process event
        try:
            result = await self._process_event(x_github_event, data)

            return JSONResponse(
                content={"message": "Event processed successfully", "result": result},
                status_code=200,
            )

        except Exception as e:
            logger.error(
                "Failed to process webhook event",
                webhook_event_type=x_github_event,
                delivery_id=x_github_delivery,
                error=str(e),
            )

            return JSONResponse(
                content={"message": "Failed to process event", "error": str(e)},
                status_code=500,
            )

    async def _process_event(
        self, event_type: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Process a GitHub webhook event.

        Args:
            event_type: Type of GitHub event
            data: Event data

        Returns:
            Processing result
        """
        if event_type == "pull_request":
            return await self._process_pull_request_event(data)
        elif event_type == "check_suite":
            return await self._process_check_suite_event(data)
        elif event_type == "issues":
            return await self._process_issues_event(data)
        elif event_type == "push":
            return await self._process_push_event(data)
        else:
            return {"message": "Event not handled"}

    async def _process_pull_request_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Process pull request events.

        Args:
            data: Pull request event data

        Returns:
            Processing result
        """
        action = data.get("action")
        pr_data = data.get("pull_request", {})
        repo_data = data.get("repository", {})

        # Only process relevant actions
        if action not in ["opened", "synchronize", "reopened", "ready_for_review"]:
            return {"message": f"PR action '{action}' not relevant"}

        # Get PR processor and process the PR (it will handle Renovate filtering and dashboard logic)
        pr_processor = self._get_pr_processor()
        result = await pr_processor.process_pr_event(action, pr_data, repo_data)

        return result

    async def _process_check_suite_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Process check suite events.

        Args:
            data: Check suite event data

        Returns:
            Processing result
        """
        action = data.get("action")
        check_suite = data.get("check_suite", {})
        repo_data = data.get("repository", {})

        # Only process completed check suites
        if action != "completed":
            return {"message": f"Check suite action '{action}' not relevant"}

        # Find related PRs
        pull_requests = check_suite.get("pull_requests", [])

        if not pull_requests:
            return {"message": "No PRs associated with check suite"}

        # Process each PR
        pr_processor = self._get_pr_processor()
        results = []

        for pr_data in pull_requests:
            # Check if PR is from Renovate
            user_login = pr_data.get("user", {}).get("login", "")
            if not user_login.startswith("renovate"):
                continue

            result = await pr_processor.process_check_suite_completion(
                check_suite, pr_data, repo_data
            )
            results.append(result)

        return {"message": "Check suite processed", "results": results}

    async def _process_issues_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Process issues events.

        Args:
            data: Issues event data

        Returns:
            Processing result
        """
        action = data.get("action")
        issue_data = data.get("issue", {})
        repo_data = data.get("repository", {})

        # Only process dashboard issues
        issue_title = issue_data.get("title", "")
        if settings.dashboard_issue_title not in issue_title:
            return {"message": "Issue not a dashboard issue"}

        # Log issue event
        logger.info(
            "Dashboard issue event",
            action=action,
            issue_number=issue_data.get("number"),
            repository=repo_data.get("full_name"),
        )

        return {"message": "Dashboard issue event logged"}

    async def _process_push_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Process push events.

        Args:
            data: Push event data

        Returns:
            Processing result
        """
        ref = data.get("ref", "")
        repo_data = data.get("repository", {})

        # Only process main branch pushes
        if ref != "refs/heads/main":
            return {"message": "Push not to main branch"}

        logger.info(
            "Main branch push event",
            repository=repo_data.get("full_name"),
            commits=len(data.get("commits", [])),
        )

        return {"message": "Push event logged"}

    async def webhook_info(self) -> JSONResponse:
        """
        Get webhook information.

        Returns:
            Webhook information
        """
        return JSONResponse(
            content={
                "message": "GitHub Webhook Listener",
                "supported_events": list(self.supported_events),
                "version": "0.1.0",
            }
        )
