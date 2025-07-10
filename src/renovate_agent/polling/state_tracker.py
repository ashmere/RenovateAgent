"""
Polling state tracker for the Renovate PR Assistant.

This module tracks polling state and prevents duplicate processing
of PRs across webhook and polling modes.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, cast

import structlog

from ..config import Settings
from ..github_client import GitHubClient
from ..issue_manager import IssueStateManager

logger = structlog.get_logger(__name__)


class PRState:
    """Represents the current state of a PR for delta detection."""

    def __init__(
        self,
        pr_number: str,
        state: str,
        updated_at: str,
        head_sha: str,
        mergeable_state: str | None = None,
        check_runs_conclusion: str | None = None,
        has_conflicts: bool = False,
    ):
        self.pr_number = pr_number
        self.state = state
        self.updated_at = updated_at
        self.head_sha = head_sha
        self.mergeable_state = mergeable_state or "unknown"
        self.check_runs_conclusion = check_runs_conclusion or "pending"
        self.has_conflicts = has_conflicts

    def to_hash(self) -> str:
        """Calculate a hash of the current PR state."""
        state_string = f"{self.state}:{self.updated_at}:{self.head_sha}:{self.mergeable_state}:{self.check_runs_conclusion}:{self.has_conflicts}"
        return hashlib.sha256(state_string.encode()).hexdigest()

    def has_changed(self, other: "PRState") -> bool:
        """Check if this PR state has changed compared to another state."""
        return self.to_hash() != other.to_hash()

    def is_actionable_change(self, other: "PRState") -> bool:
        """Check if the change is actionable (requires processing)."""
        if not self.has_changed(other):
            return False

        # Check for meaningful changes that would affect processing
        actionable_changes = [
            self.state != other.state,  # State change (open/closed)
            self.head_sha != other.head_sha,  # New commits
            self.mergeable_state != other.mergeable_state,  # Merge status change
            self.check_runs_conclusion
            != other.check_runs_conclusion,  # Check status change
            self.has_conflicts != other.has_conflicts,  # Conflict status change
        ]

        return any(actionable_changes)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "pr_number": self.pr_number,
            "state": self.state,
            "updated_at": self.updated_at,
            "head_sha": self.head_sha,
            "mergeable_state": self.mergeable_state,
            "check_runs_conclusion": self.check_runs_conclusion,
            "has_conflicts": self.has_conflicts,
            "state_hash": self.to_hash(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PRState":
        """Create PRState from dictionary."""
        return cls(
            pr_number=data["pr_number"],
            state=data["state"],
            updated_at=data["updated_at"],
            head_sha=data["head_sha"],
            mergeable_state=data.get("mergeable_state"),
            check_runs_conclusion=data.get("check_runs_conclusion"),
            has_conflicts=data.get("has_conflicts", False),
        )

    @classmethod
    def from_pr_object(cls, pr: Any) -> "PRState":
        """Create PRState from GitHub PR object."""
        try:
            # Get mergeable state
            mergeable_state = getattr(pr, "mergeable_state", None)

            # Get check runs conclusion
            check_runs_conclusion = None
            if hasattr(pr, "get_check_runs"):
                try:
                    check_runs = list(pr.get_check_runs())
                    if check_runs:
                        # Get overall conclusion from check runs
                        conclusions = [
                            cr.conclusion for cr in check_runs if cr.conclusion
                        ]
                        if conclusions:
                            if any(c == "failure" for c in conclusions):
                                check_runs_conclusion = "failure"
                            elif any(c == "cancelled" for c in conclusions):
                                check_runs_conclusion = "cancelled"
                            elif all(c == "success" for c in conclusions):
                                check_runs_conclusion = "success"
                            else:
                                check_runs_conclusion = "pending"
                except Exception as e:
                    logger.debug(
                        "Could not get check runs status",
                        pr_number=pr.number,
                        error=str(e),
                    )

            # Check for merge conflicts
            has_conflicts = mergeable_state == "dirty" if mergeable_state else False

            return cls(
                pr_number=str(pr.number),
                state=pr.state,
                updated_at=pr.updated_at.isoformat(),
                head_sha=pr.head.sha,
                mergeable_state=mergeable_state,
                check_runs_conclusion=check_runs_conclusion,
                has_conflicts=has_conflicts,
            )
        except Exception as e:
            logger.error("Failed to create PRState from PR object", error=str(e))
            # Return minimal state
            return cls(
                pr_number=str(pr.number),
                state=pr.state,
                updated_at=datetime.now().isoformat(),
                head_sha=getattr(pr.head, "sha", "unknown"),
                has_conflicts=False,
            )


class PollingStateTracker:
    """
    Tracks polling state and prevents duplicate processing.

    This class manages state for polling operations, tracks processed PRs,
    and provides delta detection to minimize unnecessary processing.
    """

    def __init__(self, github_client: GitHubClient, settings: Settings):
        """
        Initialize the polling state tracker.

        Args:
            github_client: GitHub API client
            settings: Application settings
        """
        self.github_client = github_client
        self.settings = settings
        self.issue_manager = IssueStateManager(github_client, settings)

        # State caches for delta detection
        self._pr_states_cache: dict[str, dict[str, PRState]] = (
            {}
        )  # repo -> {pr_number -> PRState}
        self._processed_prs_cache: dict[str, set[str]] = {}  # repo -> {pr_numbers}

    async def get_last_poll_time(self, repo_name: str) -> datetime | None:
        """
        Get the last poll time for a repository.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Last poll timestamp or None if never polled
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            polling_data = await self._extract_polling_data(dashboard_issue)
            last_poll_str = polling_data.get("last_poll_time")

            if last_poll_str:
                return datetime.fromisoformat(last_poll_str.replace("Z", "+00:00"))

            return None

        except Exception as e:
            logger.error(
                "Failed to get last poll time",
                repository=repo_name,
                error=str(e),
            )
            return None

    async def update_last_poll_time(self, repo_name: str, poll_time: datetime) -> bool:
        """
        Update the last poll time for a repository.

        Args:
            repo_name: Full repository name (org/repo)
            poll_time: Timestamp of the poll

        Returns:
            True if successful
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            # Get existing dashboard data
            existing_data = await self._extract_dashboard_data(dashboard_issue)

            # Update polling metadata
            if "polling_metadata" not in existing_data:
                existing_data["polling_metadata"] = {}

            existing_data["polling_metadata"].update(
                {
                    "last_poll_time": poll_time.isoformat(),
                    "last_updated": datetime.now().isoformat(),
                }
            )

            # Update the dashboard issue with new data
            await self._update_dashboard_with_polling_data(
                repo, dashboard_issue, existing_data
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to update last poll time",
                repository=repo_name,
                error=str(e),
            )
            return False

    async def get_pr_states(self, repo_name: str) -> dict[str, PRState]:
        """
        Get stored PR states for a repository.

        Args:
            repo_name: Full repository name (org/repo)

        Returns:
            Dictionary mapping PR numbers to their states
        """
        try:
            # Check cache first
            if repo_name in self._pr_states_cache:
                return self._pr_states_cache[repo_name]

            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            polling_data = await self._extract_polling_data(dashboard_issue)
            pr_states_data = polling_data.get("pr_states", {})

            # Convert stored data back to PRState objects
            pr_states = {}
            for pr_number, state_data in pr_states_data.items():
                try:
                    pr_states[pr_number] = PRState.from_dict(state_data)
                except Exception as e:
                    logger.warning(
                        "Failed to restore PR state",
                        repository=repo_name,
                        pr_number=pr_number,
                        error=str(e),
                    )

            # Cache the results
            self._pr_states_cache[repo_name] = pr_states
            return pr_states

        except Exception as e:
            logger.error(
                "Failed to get PR states",
                repository=repo_name,
                error=str(e),
            )
            return {}

    async def update_pr_states(
        self, repo_name: str, pr_states: dict[str, PRState]
    ) -> bool:
        """
        Update stored PR states for a repository.

        Args:
            repo_name: Full repository name (org/repo)
            pr_states: Dictionary mapping PR numbers to their states

        Returns:
            True if successful
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            # Get existing dashboard data
            existing_data = await self._extract_dashboard_data(dashboard_issue)

            # Update polling metadata with PR states
            if "polling_metadata" not in existing_data:
                existing_data["polling_metadata"] = {}

            # Convert PRState objects to dictionaries for storage
            pr_states_data = {
                pr_number: state.to_dict() for pr_number, state in pr_states.items()
            }

            existing_data["polling_metadata"].update(
                {
                    "pr_states": pr_states_data,
                    "pr_states_updated": datetime.now().isoformat(),
                }
            )

            # Update the dashboard issue
            await self._update_dashboard_with_polling_data(
                repo, dashboard_issue, existing_data
            )

            # Update cache
            self._pr_states_cache[repo_name] = pr_states.copy()

            return True

        except Exception as e:
            logger.error(
                "Failed to update PR states",
                repository=repo_name,
                error=str(e),
            )
            return False

    async def detect_pr_changes(
        self, repo_name: str, current_prs: list[Any]
    ) -> list[tuple[Any, str]]:
        """
        Detect changes in PRs since last poll.

        Args:
            repo_name: Full repository name (org/repo)
            current_prs: List of current PR objects

        Returns:
            List of tuples (pr_object, change_type) where change_type is:
            - "new": New PR not seen before
            - "updated": PR with meaningful changes
            - "unchanged": PR with no actionable changes
        """
        try:
            # Get stored PR states
            stored_states = await self.get_pr_states(repo_name)

            current_states = {}
            changes = []

            for pr in current_prs:
                pr_number = str(pr.number)
                current_state = PRState.from_pr_object(pr)
                current_states[pr_number] = current_state

                if pr_number not in stored_states:
                    # New PR
                    changes.append((pr, "new"))
                    logger.debug(
                        "New PR detected",
                        repository=repo_name,
                        pr_number=pr_number,
                        title=pr.title,
                    )
                else:
                    stored_state = stored_states[pr_number]

                    if current_state.is_actionable_change(stored_state):
                        # Meaningful change detected
                        changes.append((pr, "updated"))
                        logger.debug(
                            "PR state change detected",
                            repository=repo_name,
                            pr_number=pr_number,
                            title=pr.title,
                            old_hash=stored_state.to_hash()[:8],
                            new_hash=current_state.to_hash()[:8],
                        )
                    else:
                        # No actionable changes
                        changes.append((pr, "unchanged"))

            # Update stored states with current states
            await self.update_pr_states(repo_name, current_states)

            logger.debug(
                "Delta detection completed",
                repository=repo_name,
                total_prs=len(current_prs),
                new_prs=len([c for c in changes if c[1] == "new"]),
                updated_prs=len([c for c in changes if c[1] == "updated"]),
                unchanged_prs=len([c for c in changes if c[1] == "unchanged"]),
            )

            return changes

        except Exception as e:
            logger.error(
                "Failed to detect PR changes",
                repository=repo_name,
                error=str(e),
            )
            # Return all PRs as "new" if delta detection fails
            return [(pr, "new") for pr in current_prs]

    async def is_pr_processed(self, repo_name: str, pr_number: str) -> bool:
        """
        Check if a PR has been processed.

        Args:
            repo_name: Full repository name (org/repo)
            pr_number: PR number

        Returns:
            True if PR has been processed
        """
        try:
            # Check cache first
            if repo_name in self._processed_prs_cache:
                return pr_number in self._processed_prs_cache[repo_name]

            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            polling_data = await self._extract_polling_data(dashboard_issue)
            processed_prs = set(polling_data.get("processed_prs", []))

            # Update cache
            self._processed_prs_cache[repo_name] = processed_prs

            return pr_number in processed_prs

        except Exception as e:
            logger.error(
                "Failed to check if PR is processed",
                repository=repo_name,
                pr_number=pr_number,
                error=str(e),
            )
            return False

    async def mark_pr_processed(self, repo_name: str, pr_number: str) -> bool:
        """
        Mark a PR as processed.

        Args:
            repo_name: Full repository name (org/repo)
            pr_number: PR number

        Returns:
            True if successful
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            # Get existing data
            existing_data = await self._extract_dashboard_data(dashboard_issue)
            polling_data = existing_data.get("polling_metadata", {})
            processed_prs = set(polling_data.get("processed_prs", []))

            # Add PR to processed list
            processed_prs.add(pr_number)

            # Update polling metadata
            if "polling_metadata" not in existing_data:
                existing_data["polling_metadata"] = {}

            existing_data["polling_metadata"].update(
                {
                    "processed_prs": list(processed_prs),
                    "processed_prs_updated": datetime.now().isoformat(),
                }
            )

            # Update dashboard
            await self._update_dashboard_with_polling_data(
                repo, dashboard_issue, existing_data
            )

            # Update cache
            if repo_name not in self._processed_prs_cache:
                self._processed_prs_cache[repo_name] = set()
            self._processed_prs_cache[repo_name].add(pr_number)

            return True

        except Exception as e:
            logger.error(
                "Failed to mark PR as processed",
                repository=repo_name,
                pr_number=pr_number,
                error=str(e),
            )
            return False

    async def record_polling_metrics(
        self,
        repo_name: str,
        metrics: dict[str, Any],
    ) -> bool:
        """
        Record polling metrics for a repository.

        Args:
            repo_name: Full repository name (org/repo)
            metrics: Polling metrics dictionary

        Returns:
            True if successful
        """
        try:
            repo = await self.github_client.get_repo(repo_name)
            dashboard_issue = await self.issue_manager.get_or_create_dashboard_issue(
                repo
            )

            # Get existing dashboard data
            existing_data = await self._extract_dashboard_data(dashboard_issue)

            # Update polling metadata
            if "polling_metadata" not in existing_data:
                existing_data["polling_metadata"] = {}

            existing_data["polling_metadata"].update(
                {
                    "metrics": metrics,
                    "metrics_updated": datetime.now().isoformat(),
                }
            )

            # Update the dashboard issue
            await self._update_dashboard_with_polling_data(
                repo, dashboard_issue, existing_data
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to record polling metrics",
                repository=repo_name,
                error=str(e),
            )
            return False

    async def _extract_polling_data(self, dashboard_issue: Any) -> dict[str, Any]:
        """
        Extract polling data from dashboard issue.

        Args:
            dashboard_issue: GitHub issue object

        Returns:
            Polling data dictionary
        """
        try:
            # Parse JSON data from issue body
            dashboard_data = await self._extract_dashboard_data(dashboard_issue)
            return cast(dict[str, Any], dashboard_data.get("polling_metadata", {}))

        except Exception as e:
            logger.error(
                "Failed to extract polling data",
                issue_number=dashboard_issue.number,
                error=str(e),
            )
            return {}

    async def _extract_dashboard_data(self, dashboard_issue: Any) -> dict[str, Any]:
        """
        Extract dashboard data from issue body.

        Args:
            dashboard_issue: GitHub issue object

        Returns:
            Dashboard data dictionary
        """
        try:
            issue_body = dashboard_issue.body or ""

            # Find JSON data in HTML comment (matching issue manager format)
            import re

            json_match = re.search(
                r"<!-- DASHBOARD_DATA\n(.*?)\n-->", issue_body, re.DOTALL
            )

            if json_match:
                json_content = json_match.group(1)
                data = json.loads(json_content)
                return cast(dict[str, Any], data if isinstance(data, dict) else {})

            return {}

        except (json.JSONDecodeError, Exception) as e:
            logger.error(
                "Failed to parse dashboard data",
                issue_number=dashboard_issue.number,
                error=str(e),
            )
            return {}

    async def _update_dashboard_with_polling_data(
        self,
        repo: Any,
        dashboard_issue: Any,
        updated_data: dict[str, Any],
    ) -> None:
        """
        Update dashboard issue with polling data.

        Args:
            repo: Repository object
            dashboard_issue: Dashboard issue object
            updated_data: Updated dashboard data
        """
        try:
            # Generate updated issue body using the issue manager
            updated_body = await self.issue_manager._generate_dashboard_body(
                updated_data
            )

            # Update the issue
            await self.github_client.update_issue(
                repo=repo,
                issue_number=dashboard_issue.number,
                body=updated_body,
            )

        except Exception as e:
            logger.error(
                "Failed to update dashboard with polling data",
                repository=repo.full_name,
                issue_number=dashboard_issue.number,
                error=str(e),
            )
