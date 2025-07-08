"""
GitHub API client for the Renovate PR Assistant.

This module provides a robust GitHub API client with authentication, rate limiting,
and error handling for GitHub App integration.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

import httpx
import jwt
import structlog
from github import Github, GithubException
from github.CheckRun import CheckRun
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository

from .exceptions import AuthenticationError, GitHubAPIError

logger = structlog.get_logger(__name__)


class GitHubClient:
    """
    GitHub API client with authentication and rate limiting.

    This client handles GitHub App authentication, rate limiting, and provides
    convenient methods for interacting with PRs, issues, and repository data.
    """

    def __init__(self, config: Any) -> None:
        """
        Initialize the GitHub client.

        Args:
            config: GitHub App configuration or Settings object
        """
        self.config = config
        self._github: Optional[Github] = None
        self._installation_id: Optional[int] = None
        self._rate_limit_reset_time: Optional[float] = None
        self._rate_limit_remaining: Optional[int] = None

    async def _get_github_instance(self) -> Github:
        """Get authenticated GitHub instance."""
        if self._github is None:
            await self._authenticate()
        if self._github is None:
            raise AuthenticationError("Failed to authenticate with GitHub")
        return self._github

    async def _authenticate(self) -> None:
        """Authenticate with GitHub using App authentication or PAT."""
        try:
            # Check if we have a personal access token (development mode)
            pat = getattr(self.config, "github_personal_access_token", None) or getattr(
                self.config, "personal_access_token", None
            )
            if pat:
                self._github = Github(pat)
                logger.info("GitHub authentication successful (PAT mode)")
                return

            # GitHub App authentication (production mode)
            # Read private key
            private_key_path = Path(self.config.private_key_path)
            if not private_key_path.exists():
                raise AuthenticationError(f"Private key not found: {private_key_path}")

            with open(private_key_path) as f:
                private_key = f.read()

            # Create JWT token
            jwt_token = self._create_jwt_token(private_key)

            # Get installation ID
            installation_id = await self._get_installation_id(jwt_token)

            # Get installation access token
            access_token = await self._get_installation_access_token(
                jwt_token, installation_id
            )

            # Create authenticated GitHub instance
            self._github = Github(access_token)
            self._installation_id = installation_id

            logger.info(
                "GitHub authentication successful (GitHub App mode)",
                installation_id=installation_id,
            )

        except Exception as e:
            logger.error("GitHub authentication failed", error=str(e))
            raise AuthenticationError(f"Failed to authenticate with GitHub: {e}") from e

    def _create_jwt_token(self, private_key: str) -> str:
        """Create JWT token for GitHub App authentication."""
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + 600,  # 10 minutes
            "iss": self.config.app_id,
        }

        token = cast(
            Union[str, bytes], jwt.encode(payload, private_key, algorithm="RS256")
        )
        # Handle jwt.encode returning bytes in some versions
        if isinstance(token, bytes):
            return token.decode("utf-8")
        return token

    async def _get_installation_id(self, jwt_token: str) -> int:
        """Get installation ID for the organization."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/app/installations",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )

            if response.status_code != 200:
                raise AuthenticationError(
                    f"Failed to get installations: {response.text}"
                )

            installations = response.json()

            for installation in installations:
                if (
                    installation.get("account", {}).get("login")
                    == self.config.organization
                ):
                    installation_id = installation["id"]
                    if isinstance(installation_id, int):
                        return installation_id
                    raise AuthenticationError(
                        f"Invalid installation ID type: " f"{type(installation_id)}"
                    )

            raise AuthenticationError(
                f"No installation found for organization: "
                f"{self.config.organization}"
            )

    async def _get_installation_access_token(
        self, jwt_token: str, installation_id: int
    ) -> str:
        """Get installation access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/app/installations/"
                f"{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )

            if response.status_code != 201:
                raise AuthenticationError(
                    f"Failed to get access token: {response.text}"
                )

            token = response.json()["token"]
            if isinstance(token, str):
                return token
            raise AuthenticationError(f"Invalid token type: {type(token)}")

    async def _check_rate_limit(self) -> None:
        """Check and handle rate limiting."""
        if self._rate_limit_remaining is not None and self._rate_limit_remaining <= 10:
            if (
                self._rate_limit_reset_time
                and time.time() < self._rate_limit_reset_time
            ):
                sleep_time = self._rate_limit_reset_time - time.time()
                logger.warning(
                    "Rate limit approaching, sleeping",
                    sleep_time=sleep_time,
                    remaining=self._rate_limit_remaining,
                )
                await asyncio.sleep(sleep_time)

    def _update_rate_limit_info(self, github_instance: Any) -> None:
        """Update rate limit information from GitHub response."""
        try:
            # Use the GitHub instance directly for rate limit info
            if isinstance(github_instance, Github):
                rate_limit = github_instance.get_rate_limit()
                self._rate_limit_remaining = rate_limit.core.remaining
                self._rate_limit_reset_time = rate_limit.core.reset.timestamp()
            else:
                # Fallback for repository objects
                github_obj = (
                    github_instance._requester._Github__requester
                    if hasattr(github_instance, "_requester")
                    else None
                )
                if github_obj:
                    rate_limit = github_obj.get_rate_limit()
                    self._rate_limit_remaining = rate_limit.core.remaining
                    self._rate_limit_reset_time = rate_limit.core.reset.timestamp()
        except Exception as e:
            logger.warning("Failed to get rate limit info", error=str(e))

    async def get_repo(self, full_name: str) -> Repository:
        """
        Get repository by full name.

        Args:
            full_name: Repository full name (owner/repo)

        Returns:
            Repository object
        """
        await self._check_rate_limit()

        try:
            github_instance = await self._get_github_instance()
            repo = github_instance.get_repo(full_name)
            self._update_rate_limit_info(github_instance)
            return repo
        except GithubException as e:
            logger.error("Failed to get repository", repo=full_name, error=str(e))
            raise GitHubAPIError(f"Failed to get repository {full_name}: {e}") from e

    async def get_pr(self, repo: Repository, pr_number: int) -> PullRequest:
        """
        Get pull request by number.

        Args:
            repo: Repository object
            pr_number: Pull request number

        Returns:
            PullRequest object
        """
        await self._check_rate_limit()

        try:
            pr = repo.get_pull(pr_number)
            self._update_rate_limit_info(self._github)
            return pr
        except GithubException as e:
            logger.error(
                "Failed to get pull request",
                repo=repo.full_name,
                pr_number=pr_number,
                error=str(e),
            )
            raise GitHubAPIError(f"Failed to get PR {pr_number}: {e}") from e

    async def get_pr_checks(self, repo: Repository, pr: PullRequest) -> List[CheckRun]:
        """
        Get all checks for a pull request.

        Args:
            repo: Repository object
            pr: Pull request object

        Returns:
            List of CheckRun objects
        """
        await self._check_rate_limit()

        try:
            commit = repo.get_commit(pr.head.sha)
            check_runs = list(commit.get_check_runs())

            # Also get status checks (older API)
            status_checks = list(commit.get_statuses())

            self._update_rate_limit_info(self._github)

            logger.info(
                "Retrieved PR checks",
                repo=repo.full_name,
                pr_number=pr.number,
                check_runs=len(check_runs),
                status_checks=len(status_checks),
            )

            return check_runs
        except GithubException as e:
            logger.error(
                "Failed to get PR checks",
                repo=repo.full_name,
                pr_number=pr.number,
                error=str(e),
            )
            raise GitHubAPIError(f"Failed to get PR checks: {e}") from e

    async def approve_pr(
        self,
        repo: Repository,
        pr_number: int,
        review_body: str = "Auto-approved by Renovate PR Assistant",
    ) -> bool:
        """
        Approve a pull request.

        Args:
            repo: Repository object
            pr_number: Pull request number
            review_body: Review body text

        Returns:
            True if successful
        """
        await self._check_rate_limit()

        try:
            pr = await self.get_pr(repo, pr_number)

            # Create approval review
            pr.create_review(body=review_body, event="APPROVE")

            logger.info(
                "PR approved successfully", repo=repo.full_name, pr_number=pr_number
            )

            return True
        except GithubException as e:
            logger.error(
                "Failed to approve PR",
                repo=repo.full_name,
                pr_number=pr_number,
                error=str(e),
            )
            raise GitHubAPIError(f"Failed to approve PR {pr_number}: {e}") from e

    async def create_issue(
        self,
        repo: Repository,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
    ) -> Issue:
        """
        Create a new issue.

        Args:
            repo: Repository object
            title: Issue title
            body: Issue body
            labels: Optional list of labels

        Returns:
            Issue object
        """
        await self._check_rate_limit()

        try:
            issue = repo.create_issue(title=title, body=body, labels=labels or [])

            logger.info(
                "Issue created successfully",
                repo=repo.full_name,
                issue_number=issue.number,
                title=title,
            )

            return issue
        except GithubException as e:
            logger.error(
                "Failed to create issue", repo=repo.full_name, title=title, error=str(e)
            )
            raise GitHubAPIError(f"Failed to create issue: {e}") from e

    async def update_issue(
        self,
        repo: Repository,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
    ) -> Issue:
        """
        Update an existing issue.

        Args:
            repo: Repository object
            issue_number: Issue number
            title: New title (optional)
            body: New body (optional)
            state: New state (optional)

        Returns:
            Updated Issue object
        """
        await self._check_rate_limit()

        try:
            issue = repo.get_issue(issue_number)

            if title:
                issue.edit(title=title)
            if body:
                issue.edit(body=body)
            if state:
                issue.edit(state=state)

            logger.info(
                "Issue updated successfully",
                repo=repo.full_name,
                issue_number=issue_number,
            )

            return issue
        except GithubException as e:
            logger.error(
                "Failed to update issue",
                repo=repo.full_name,
                issue_number=issue_number,
                error=str(e),
            )
            raise GitHubAPIError(f"Failed to update issue {issue_number}: {e}") from e

    async def find_issue_by_title(
        self, repo: Repository, title: str
    ) -> Optional[Issue]:
        """
        Find an issue by title.

        Args:
            repo: Repository object
            title: Issue title to search for

        Returns:
            Issue object if found, None otherwise
        """
        await self._check_rate_limit()

        try:
            issues = repo.get_issues(state="open")

            for issue in issues:
                if issue.title == title:
                    logger.info(
                        "Found issue by title",
                        repo=repo.full_name,
                        issue_number=issue.number,
                        title=title,
                    )
                    return issue

            logger.info("Issue not found by title", repo=repo.full_name, title=title)
            return None
        except GithubException as e:
            logger.error(
                "Failed to search for issue",
                repo=repo.full_name,
                title=title,
                error=str(e),
            )
            raise GitHubAPIError(f"Failed to search for issue: {e}") from e

    async def commit_file(
        self,
        repo: Repository,
        file_path: str,
        content: str,
        message: str,
        branch: str = "main",
    ) -> bool:
        """
        Commit a file to repository.

        Args:
            repo: Repository object
            file_path: Path to file in repository
            content: File content
            message: Commit message
            branch: Branch name

        Returns:
            True if successful
        """
        await self._check_rate_limit()

        try:
            # Try to get existing file
            try:
                file_info = repo.get_contents(file_path, ref=branch)
                # Handle case where get_contents returns a list instead
                # of a single file
                if isinstance(file_info, list):
                    if file_info:
                        file_sha = file_info[0].sha
                    else:
                        # Empty list means file not found, raise to trigger creation
                        raise GithubException(404, "File not found", {})
                else:
                    file_sha = file_info.sha

                repo.update_file(
                    path=file_path,
                    message=message,
                    content=content,
                    sha=file_sha,
                    branch=branch,
                )
            except GithubException:
                # File doesn't exist, create it
                repo.create_file(
                    path=file_path, message=message, content=content, branch=branch
                )

            logger.info(
                "File committed successfully",
                repo=repo.full_name,
                file_path=file_path,
                branch=branch,
            )

            return True
        except GithubException as e:
            logger.error(
                "Failed to commit file",
                repo=repo.full_name,
                file_path=file_path,
                branch=branch,
                error=str(e),
            )
            raise GitHubAPIError(f"Failed to commit file {file_path}: {e}") from e

    async def is_renovate_pr(self, pr: PullRequest) -> bool:
        """
        Check if a PR is from Renovate.

        Args:
            pr: Pull request object

        Returns:
            True if PR is from Renovate
        """
        user_login = pr.user.login.lower()
        pr_title = pr.title.lower()
        pr_body = (pr.body or "").lower()
        branch_name = pr.head.ref.lower()

        # Check for Renovate indicators
        renovate_indicators = [
            # User login patterns
            "renovate" in user_login,
            user_login.startswith("renovate"),
            user_login.endswith("[bot]") and "renovate" in user_login,
            # Title patterns
            "update dependency" in pr_title,
            "chore(deps)" in pr_title,
            "fix(deps)" in pr_title,
            "renovate" in pr_title,
            # Branch patterns
            branch_name.startswith("renovate/"),
            "renovate" in branch_name,
            # Body patterns
            "renovate" in pr_body,
            "this pr contains the following updates" in pr_body,
        ]

        # Must be a bot and have at least one Renovate indicator
        is_bot = pr.user.type == "Bot"
        has_renovate_indicator = any(renovate_indicators)

        return is_bot and has_renovate_indicator

    async def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Get current rate limit information.

        Returns:
            Dictionary with rate limit information
        """
        try:
            github_instance = await self._get_github_instance()
            rate_limit = github_instance.get_rate_limit()

            return {
                "core": {
                    "limit": rate_limit.core.limit,
                    "remaining": rate_limit.core.remaining,
                    "reset": rate_limit.core.reset.isoformat(),
                },
                "search": {
                    "limit": rate_limit.search.limit,
                    "remaining": rate_limit.search.remaining,
                    "reset": rate_limit.search.reset.isoformat(),
                },
            }
        except Exception as e:
            logger.error("Failed to get rate limit info", error=str(e))
            return {"error": str(e)}

    async def get_organization_repositories(
        self, org_name: str, include_archived: bool = False
    ) -> List[Repository]:
        """
        Get all repositories for an organization with filtering.

        Args:
            org_name: Organization name
            include_archived: Whether to include archived repositories

        Returns:
            List of repository objects
        """
        await self._check_rate_limit()

        try:
            github_instance = await self._get_github_instance()
            org = github_instance.get_organization(org_name)

            repositories = []
            for repo in org.get_repos():
                # Filter out archived repositories if not including them
                if repo.archived and not include_archived:
                    continue
                repositories.append(repo)

            self._update_rate_limit_info(github_instance)
            return repositories

        except GithubException as e:
            logger.error(
                "Failed to get organization repositories", org=org_name, error=str(e)
            )
            raise GitHubAPIError(
                f"Failed to get repositories for {org_name}: {e}"
            ) from e

    def should_process_repository(self, repo: Repository) -> bool:
        """
        Check if a repository should be processed based on configuration.

        Args:
            repo: Repository object

        Returns:
            True if repository should be processed
        """
        from .config import get_settings

        settings = get_settings()

        # Extract repo name without org prefix
        repo_name = repo.name

        return settings.should_process_repository(repo_name, repo.archived)
