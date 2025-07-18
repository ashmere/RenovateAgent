"""
PR processing engine for the Renovate PR Assistant.

This module contains the core logic for analyzing and processing Renovate PRs,
including automatic approval and dependency fixing.
"""

from datetime import datetime
from typing import Any

import structlog
from github.PullRequest import PullRequest
from github.Repository import Repository

from .config import Settings
from .dependency_fixer import DependencyFixerFactory
from .exceptions import PRProcessingError
from .github_client import GitHubClient

logger = structlog.get_logger(__name__)


class PRProcessor:
    """
    Core PR processing engine.

    This class handles the analysis and processing of Renovate PRs,
    including automatic approval and dependency fixing.
    """

    def __init__(self, github_client: GitHubClient, settings: Settings):
        """
        Initialize the PR processor.

        Args:
            github_client: GitHub API client
            settings: Application settings
        """
        self.github_client = github_client
        self.settings = settings
        self.dependency_fixer_factory = DependencyFixerFactory(settings)

    async def process_pr_webhook(
        self, repo_name: str, pr_number: int, webhook_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Process a PR webhook event from the serverless function.

        Args:
            repo_name: Repository name (e.g., "owner/repo")
            pr_number: Pull request number
            webhook_payload: Full GitHub webhook payload

        Returns:
            Processing result
        """
        try:
            # Extract action from payload
            action = webhook_payload.get("action", "unknown")

            # Extract PR and repository data from payload
            pr_data = webhook_payload.get("pull_request", {})
            repo_data = webhook_payload.get("repository", {})

            # Ensure we have the PR number and repo name
            pr_data["number"] = pr_number
            repo_data["full_name"] = repo_name

            logger.info(
                "Processing webhook for PR",
                action=action,
                pr_number=pr_number,
                repository=repo_name,
            )

            # Route to appropriate handler based on webhook type
            if "pull_request" in webhook_payload:
                return await self.process_pr_event(action, pr_data, repo_data)
            elif "check_suite" in webhook_payload:
                check_suite = webhook_payload.get("check_suite", {})
                return await self.process_check_suite_completion(
                    check_suite, pr_data, repo_data
                )
            else:
                return {
                    "success": True,
                    "message": "Unsupported webhook event type",
                    "processed": False,
                }

        except Exception as e:
            logger.error(
                "Failed to process webhook",
                pr_number=pr_number,
                repository=repo_name,
                error=str(e),
            )
            return {
                "success": False,
                "message": f"Failed to process webhook: {str(e)}",
                "processed": False,
            }

    async def process_pr_event(
        self, action: str, pr_data: dict[str, Any], repo_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Process a pull request event.

        Args:
            action: PR action (opened, synchronize, etc.)
            pr_data: Pull request data
            repo_data: Repository data

        Returns:
            Processing result
        """
        pr_number = pr_data.get("number")
        repo_name = repo_data.get("full_name")

        # Validate required data
        if not isinstance(pr_number, int):
            raise PRProcessingError(
                f"Invalid PR number: {pr_number}",
                pr_number=pr_number,
                repo_name=repo_name,
            )

        if not isinstance(repo_name, str):
            raise PRProcessingError(
                f"Invalid repository name: {repo_name}",
                pr_number=pr_number,
                repo_name=repo_name,
            )

        logger.info(
            "Processing PR event",
            action=action,
            pr_number=pr_number,
            repository=repo_name,
        )

        try:
            # Get repository and PR objects
            repo = await self.github_client.get_repo(repo_name)

            # Check if repository should be processed
            if not self.github_client.should_process_repository(repo):
                return {
                    "message": "Repository not in allowlist or is archived",
                    "action": "ignored",
                }

            pr = await self.github_client.get_pr(repo, pr_number)

            # Check if this is a Renovate PR or if we should process anyway
            is_renovate_pr = await self.github_client.is_renovate_pr(pr)
            should_create_dashboard = self.settings.should_create_dashboard(
                repo.full_name, is_renovate_pr
            )

            # If not a Renovate PR and we shouldn't create dashboard, ignore
            if not is_renovate_pr and not should_create_dashboard:
                return {"message": "Not a Renovate PR", "action": "ignored"}

            # Create or update dashboard if configured to do so
            if should_create_dashboard:
                await self._ensure_dashboard_exists(repo, pr, is_renovate_pr)

            # Only process Renovate PRs for approval logic
            if is_renovate_pr:
                # Process based on action
                if action in ["opened", "synchronize", "reopened", "ready_for_review"]:
                    return await self._process_pr_for_approval(repo, pr)
                else:
                    return {"message": f"Action '{action}' not handled"}
            else:
                return {
                    "message": "Dashboard updated for non-Renovate PR",
                    "action": "dashboard_updated",
                }

        except Exception as e:
            logger.error(
                "Failed to process PR event",
                action=action,
                pr_number=pr_number,
                repository=repo_name,
                error=str(e),
            )
            raise PRProcessingError(
                f"Failed to process PR event: {e}",
                pr_number=pr_number,
                repo_name=repo_name,
            ) from e

    async def process_check_suite_completion(
        self,
        check_suite: dict[str, Any],
        pr_data: dict[str, Any],
        repo_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Process check suite completion event.

        Args:
            check_suite: Check suite data
            pr_data: Pull request data
            repo_data: Repository data

        Returns:
            Processing result
        """
        pr_number = pr_data.get("number")
        repo_name = repo_data.get("full_name")

        # Validate required data
        if not isinstance(pr_number, int):
            raise PRProcessingError(
                f"Invalid PR number: {pr_number}",
                pr_number=pr_number,
                repo_name=repo_name,
            )

        if not isinstance(repo_name, str):
            raise PRProcessingError(
                f"Invalid repository name: {repo_name}",
                pr_number=pr_number,
                repo_name=repo_name,
            )

        logger.info(
            "Processing check suite completion",
            pr_number=pr_number,
            repository=repo_name,
            conclusion=check_suite.get("conclusion"),
        )

        try:
            # Get repository and PR objects
            repo = await self.github_client.get_repo(repo_name)

            # Check if repository should be processed
            if not self.github_client.should_process_repository(repo):
                return {
                    "message": "Repository not in allowlist or is archived",
                    "action": "ignored",
                }

            pr = await self.github_client.get_pr(repo, pr_number)

            # Verify this is a Renovate PR
            if not await self.github_client.is_renovate_pr(pr):
                return {"message": "Not a Renovate PR", "action": "ignored"}

            # Process PR for approval now that checks have completed
            return await self._process_pr_for_approval(repo, pr)

        except Exception as e:
            logger.error(
                "Failed to process check suite completion",
                pr_number=pr_number,
                repository=repo_name,
                error=str(e),
            )
            raise PRProcessingError(
                f"Failed to process check suite completion: {e}",
                pr_number=pr_number,
                repo_name=repo_name,
            ) from e

    async def _process_pr_for_approval(
        self, repo: Repository, pr: PullRequest
    ) -> dict[str, Any]:
        """
        Process a PR for potential approval.

        Args:
            repo: Repository object
            pr: Pull request object

        Returns:
            Processing result
        """
        logger.info(
            "Analyzing PR for approval",
            pr_number=pr.number,
            repository=repo.full_name,
            title=pr.title,
        )

        # Check if PR is in mergeable state
        if pr.state != "open":
            return {"message": "PR is not open", "action": "ignored"}

        if pr.draft:
            return {"message": "PR is a draft", "action": "ignored"}

        # Check if PR has merge conflicts
        if pr.mergeable is False:
            logger.info(
                "PR has merge conflicts", pr_number=pr.number, repository=repo.full_name
            )
            return {"message": "PR has merge conflicts", "action": "blocked"}

        # Get and analyze checks
        checks_result = await self._analyze_pr_checks(repo, pr)

        if checks_result["status"] == "pending":
            return {"message": "Checks are still pending", "action": "waiting"}

        if checks_result["status"] == "failed":
            # Check if this is a dependency issue we can fix
            if self.settings.enable_dependency_fixing:
                fix_result = await self._attempt_dependency_fix(repo, pr)
                if fix_result["success"]:
                    return {
                        "message": "Dependencies fixed",
                        "action": "dependency_fix_applied",
                        "details": fix_result,
                    }

            return {
                "message": "PR checks failed",
                "action": "blocked",
                "failed_checks": checks_result["failed_checks"],
            }

        if checks_result["status"] == "success":
            # All checks passed, approve the PR
            approval_result = await self._approve_pr(repo, pr)
            return {
                "message": "PR approved automatically",
                "action": "approved",
                "details": approval_result,
            }

        return {"message": "Unknown check status", "action": "ignored"}

    async def _analyze_pr_checks(
        self, repo: Repository, pr: PullRequest
    ) -> dict[str, Any]:
        """
        Analyze the status of PR checks.

        Args:
            repo: Repository object
            pr: Pull request object

        Returns:
            Check analysis result
        """
        try:
            # Get check runs
            check_runs = await self.github_client.get_pr_checks(repo, pr)

            if not check_runs:
                # No checks defined, consider as passing
                logger.info(
                    "No checks found for PR",
                    pr_number=pr.number,
                    repository=repo.full_name,
                )
                return {"status": "success", "total_checks": 0}

            # Analyze check results
            total_checks = len(check_runs)
            passed_checks = 0
            failed_checks = []
            pending_checks = []

            for check in check_runs:
                if check.status == "completed":
                    if check.conclusion == "success":
                        passed_checks += 1
                    elif check.conclusion in ["failure", "cancelled", "timed_out"]:
                        failed_checks.append(
                            {
                                "name": check.name,
                                "conclusion": check.conclusion,
                                "details_url": check.details_url,
                            }
                        )
                else:
                    pending_checks.append({"name": check.name, "status": check.status})

            logger.info(
                "PR check analysis",
                pr_number=pr.number,
                repository=repo.full_name,
                total=total_checks,
                passed=passed_checks,
                failed=len(failed_checks),
                pending=len(pending_checks),
            )

            # Determine overall status
            if pending_checks:
                return {
                    "status": "pending",
                    "total_checks": total_checks,
                    "passed_checks": passed_checks,
                    "pending_checks": pending_checks,
                }

            if failed_checks:
                return {
                    "status": "failed",
                    "total_checks": total_checks,
                    "passed_checks": passed_checks,
                    "failed_checks": failed_checks,
                }

            return {
                "status": "success",
                "total_checks": total_checks,
                "passed_checks": passed_checks,
            }

        except Exception as e:
            logger.error(
                "Failed to analyze PR checks",
                pr_number=pr.number,
                repository=repo.full_name,
                error=str(e),
            )
            # In case of error, assume checks are pending
            return {"status": "pending", "error": str(e)}

    async def _approve_pr(self, repo: Repository, pr: PullRequest) -> dict[str, Any]:
        """
        Approve a pull request.

        Args:
            repo: Repository object
            pr: Pull request object

        Returns:
            Approval result
        """
        try:
            # Create approval review
            review_body = (
                f"✅ **Auto-approved by Renovate PR Assistant**\n\n"
                f"This Renovate PR has been automatically approved because:\n"
                f"- All pre-merge checks are passing\n"
                f"- PR is from the official Renovate bot\n"
                f"- No merge conflicts detected\n\n"
                f"_Approved at {datetime.utcnow().isoformat()}Z_"
            )

            success = await self.github_client.approve_pr(repo, pr.number, review_body)

            if success:
                logger.info(
                    "PR approved successfully",
                    pr_number=pr.number,
                    repository=repo.full_name,
                )
                return {
                    "success": True,
                    "timestamp": datetime.utcnow().isoformat(),
                    "review_body": review_body,
                }
            else:
                return {"success": False, "error": "Failed to approve PR"}

        except Exception as e:
            logger.error(
                "Failed to approve PR",
                pr_number=pr.number,
                repository=repo.full_name,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

    async def _attempt_dependency_fix(
        self, repo: Repository, pr: PullRequest
    ) -> dict[str, Any]:
        """
        Attempt to fix dependency issues in a PR.

        Args:
            repo: Repository object
            pr: Pull request object

        Returns:
            Fix result
        """
        logger.info(
            "Attempting dependency fix", pr_number=pr.number, repository=repo.full_name
        )

        try:
            # Get appropriate dependency fixer
            fixer = await self.dependency_fixer_factory.get_fixer(repo)

            if not fixer:
                return {"success": False, "error": "No suitable dependency fixer found"}

            # Attempt to fix dependencies
            # First clone the repository to a temporary directory
            # Note: This is a simplified approach - a full implementation would
            # need to handle repository cloning and cleanup
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_repo_path = Path(temp_dir) / f"repo_{repo.name}"

                fix_result = await fixer.fix_dependencies(
                    repo_path=temp_repo_path, branch=pr.head.ref
                )

                if fix_result["success"]:
                    logger.info(
                        "Dependencies fixed successfully",
                        pr_number=pr.number,
                        repository=repo.full_name,
                        fixer=fixer.__class__.__name__,
                    )

                    return {
                        "success": True,
                        "fixer": fixer.__class__.__name__,
                        "changes": fix_result.get("changes", []),
                        "commit_sha": fix_result.get("commit_sha"),
                    }
                else:
                    return {
                        "success": False,
                        "error": fix_result.get("error", "Unknown error"),
                        "fixer": fixer.__class__.__name__,
                    }

        except Exception as e:
            logger.error(
                "Failed to fix dependencies",
                pr_number=pr.number,
                repository=repo.full_name,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

    async def get_pr_status(self, repo_name: str, pr_number: int) -> dict[str, Any]:
        """
        Get comprehensive status of a PR.

        Args:
            repo_name: Repository full name
            pr_number: Pull request number

        Returns:
            PR status information
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            pr = await self.github_client.get_pr(repo, pr_number)

            # Get checks status
            checks_result = await self._analyze_pr_checks(repo, pr)

            return {
                "pr_number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "draft": pr.draft,
                "mergeable": pr.mergeable,
                "user": pr.user.login,
                "is_renovate": await self.github_client.is_renovate_pr(pr),
                "checks": checks_result,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
            }

        except Exception as e:
            logger.error(
                "Failed to get PR status",
                repository=repo_name,
                pr_number=pr_number,
                error=str(e),
            )
            raise PRProcessingError(
                f"Failed to get PR status: {e}",
                pr_number=pr_number,
                repo_name=repo_name,
            ) from e

    async def _ensure_dashboard_exists(
        self, repo: Repository, pr: PullRequest, is_renovate_pr: bool
    ) -> None:
        """
        Ensure dashboard exists and is updated for the repository.

        Args:
            repo: Repository object
            pr: Pull request object
            is_renovate_pr: Whether this is a Renovate PR
        """
        try:
            from .issue_manager import IssueStateManager

            issue_manager = IssueStateManager(self.github_client, self.settings)

            # Create or get existing dashboard issue
            await issue_manager.get_or_create_dashboard_issue(repo)

            # Update dashboard with current repository state
            await issue_manager.update_dashboard_issue(repo)

            logger.info(
                "Dashboard ensured and updated for repository",
                repository=repo.full_name,
                pr_number=pr.number,
                is_renovate_pr=is_renovate_pr,
                dashboard_mode=self.settings.dashboard_creation_mode,
            )

        except Exception as e:
            logger.error(
                "Failed to ensure dashboard exists",
                repository=repo.full_name,
                pr_number=pr.number,
                error=str(e),
            )
