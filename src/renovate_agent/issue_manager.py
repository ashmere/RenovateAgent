"""
GitHub Issue State Manager for dashboard functionality.

This module manages dashboard issues in repositories, storing structured data
about open Renovate PRs and generating human-readable reports.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

import structlog
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository

from .config import Settings
from .exceptions import IssueStateError
from .github_client import GitHubClient

logger = structlog.get_logger(__name__)


class IssueStateManager:
    """
    Manager for GitHub issue-based dashboard functionality.

    This class creates and maintains dashboard issues in repositories,
    storing structured data about Renovate PRs and repository health.
    """

    def __init__(self, github_client: GitHubClient, settings: Settings):
        """
        Initialize the issue state manager.

        Args:
            github_client: GitHub API client
            settings: Application settings
        """
        self.github_client = github_client
        self.settings = settings
        self.dashboard_title = settings.dashboard_issue_title
        # Cache dashboard issues to prevent duplicates
        self._dashboard_cache: Dict[str, Issue] = {}

    async def get_or_create_dashboard_issue(self, repo: Repository) -> Issue:
        """
        Get existing dashboard issue or create a new one.

        Args:
            repo: Repository object

        Returns:
            Dashboard issue object
        """
        cache_key = repo.full_name
        
        # Return cached issue if available
        if cache_key in self._dashboard_cache:
            cached_issue = self._dashboard_cache[cache_key]
            logger.info("Using cached dashboard issue",
                       repo=repo.full_name,
                       issue_number=cached_issue.number)
            return cached_issue

        try:
            # Look for existing dashboard issues (may be multiple due to bug)
            existing_issues = await self._find_dashboard_issues(repo)

            if existing_issues:
                # Use the first (oldest) issue and close any duplicates
                primary_issue = existing_issues[0]
                
                if len(existing_issues) > 1:
                    await self._close_duplicate_dashboard_issues(
                        repo, existing_issues[1:]
                    )
                
                # Cache the primary issue
                self._dashboard_cache[cache_key] = primary_issue
                
                logger.info("Found existing dashboard issue",
                           repo=repo.full_name,
                           issue_number=primary_issue.number,
                           duplicates_closed=len(existing_issues) - 1)
                return primary_issue

            # Create new dashboard issue
            initial_data = await self._create_initial_dashboard_data(repo)
            issue_body = await self._generate_dashboard_body(initial_data)

            issue = await self.github_client.create_issue(
                repo=repo,
                title=self.dashboard_title,
                body=issue_body,
                labels=["ai-code-assistant", "dashboard", "renovate"]
            )

            # Cache the new issue
            self._dashboard_cache[cache_key] = issue

            logger.info("Created new dashboard issue",
                       repo=repo.full_name,
                       issue_number=issue.number)

            return issue

        except Exception as e:
            logger.error("Failed to get or create dashboard issue",
                        repo=repo.full_name,
                        error=str(e))
            raise IssueStateError(f"Failed to get or create dashboard issue: {e}")

    async def update_dashboard_issue(self, repo: Repository,
                                   pr_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update the dashboard issue with current repository state.

        Args:
            repo: Repository object
            pr_data: Optional PR data to include in update

        Returns:
            True if successful
        """
        try:
            # Get dashboard issue
            dashboard_issue = await self.get_or_create_dashboard_issue(repo)

            # Collect current repository data
            current_data = await self._collect_repository_data(repo, pr_data)

            # Generate updated issue body
            updated_body = await self._generate_dashboard_body(current_data)

            # Update the issue
            await self.github_client.update_issue(
                repo=repo,
                issue_number=dashboard_issue.number,
                body=updated_body
            )

            logger.info("Dashboard issue updated successfully",
                       repo=repo.full_name,
                       issue_number=dashboard_issue.number)

            return True

        except Exception as e:
            logger.error("Failed to update dashboard issue",
                        repo=repo.full_name,
                        error=str(e))
            raise IssueStateError(f"Failed to update dashboard issue: {e}")

    async def _create_initial_dashboard_data(self, repo: Repository) -> Dict[str, Any]:
        """
        Create initial dashboard data for a repository.

        Args:
            repo: Repository object

        Returns:
            Initial dashboard data
        """
        return {
            "repository": repo.full_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "open_renovate_prs": [],
            "recently_processed": [],
            "statistics": {
                "total_prs_processed": 0,
                "prs_auto_approved": 0,
                "dependency_fixes_applied": 0,
                "blocked_prs": 0
            },
            "agent_status": "active"
        }

    async def _collect_repository_data(self, repo: Repository,
                                     pr_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Collect current repository data for dashboard.

        Args:
            repo: Repository object
            pr_data: Optional specific PR data

        Returns:
            Repository dashboard data
        """
        try:
            # Get all open PRs
            open_prs = list(repo.get_pulls(state="open"))

            # Filter Renovate PRs
            renovate_prs = []
            for pr in open_prs:
                if await self.github_client.is_renovate_pr(pr):
                    pr_info = await self._extract_pr_info(pr)
                    renovate_prs.append(pr_info)

            # Get existing data from current dashboard issue
            existing_data = await self._extract_existing_data(repo)

            # Merge with existing statistics
            statistics = existing_data.get("statistics", {
                "total_prs_processed": 0,
                "prs_auto_approved": 0,
                "dependency_fixes_applied": 0,
                "blocked_prs": 0
            })

            # Update statistics if new PR data provided
            if pr_data:
                self._update_statistics(statistics, pr_data)

            # Update blocked PR count
            statistics["blocked_prs"] = len([pr for pr in renovate_prs if pr.get("status") == "blocked"])

            return {
                "repository": repo.full_name,
                "created_at": existing_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "open_renovate_prs": renovate_prs,
                "recently_processed": existing_data.get("recently_processed", [])[-10:],  # Keep last 10
                "statistics": statistics,
                "agent_status": "active"
            }

        except Exception as e:
            logger.error("Failed to collect repository data",
                        repo=repo.full_name,
                        error=str(e))
            return await self._create_initial_dashboard_data(repo)

    async def _extract_pr_info(self, pr: PullRequest) -> Dict[str, Any]:
        """
        Extract relevant information from a PR.

        Args:
            pr: Pull request object

        Returns:
            PR information dictionary
        """
        try:
            # Get PR checks
            repo = pr.base.repo
            checks = await self.github_client.get_pr_checks(repo, pr)

            # Analyze check status
            check_status = "unknown"
            if checks:
                passing = sum(1 for check in checks if check.conclusion == "success")
                total = len(checks)
                pending = sum(1 for check in checks if check.status != "completed")

                if pending > 0:
                    check_status = "pending"
                elif passing == total:
                    check_status = "passing"
                else:
                    check_status = "failing"
            else:
                check_status = "no_checks"

            # Determine overall status
            if pr.mergeable is False:
                status = "blocked"
                status_reason = "merge_conflicts"
            elif check_status == "pending":
                status = "waiting"
                status_reason = "checks_pending"
            elif check_status == "failing":
                status = "blocked"
                status_reason = "checks_failing"
            elif check_status == "passing":
                status = "ready"
                status_reason = "checks_passing"
            else:
                status = "unknown"
                status_reason = "no_checks"

            return {
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "branch": pr.head.ref,
                "created_at": pr.created_at.isoformat(),
                "updated_at": pr.updated_at.isoformat(),
                "status": status,
                "status_reason": status_reason,
                "check_status": check_status,
                "checks_total": len(checks),
                "checks_passing": sum(1 for check in checks if check.conclusion == "success"),
                "mergeable": pr.mergeable,
                "draft": pr.draft
            }

        except Exception as e:
            logger.error("Failed to extract PR info",
                        pr_number=pr.number,
                        error=str(e))
            return {
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "status": "error",
                "error": str(e)
            }

    async def _extract_existing_data(self, repo: Repository) -> Dict[str, Any]:
        """
        Extract existing data from current dashboard issue.

        Args:
            repo: Repository object

        Returns:
            Existing dashboard data or empty dict
        """
        try:
            existing_issue = await self.github_client.find_issue_by_title(
                repo, self.dashboard_title
            )

            if not existing_issue:
                return {}

            # Extract structured data from issue body
            body = existing_issue.body or ""

            # Look for JSON data in HTML comment
            json_match = re.search(r'<!-- DASHBOARD_DATA\n(.*?)\n-->', body, re.DOTALL)

            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    return data
                except json.JSONDecodeError:
                    logger.warning("Failed to parse existing dashboard data",
                                  repo=repo.full_name)

            return {}

        except Exception as e:
            logger.error("Failed to extract existing data",
                        repo=repo.full_name,
                        error=str(e))
            return {}

    def _update_statistics(self, statistics: Dict[str, Any], pr_data: Dict[str, Any]) -> None:
        """
        Update statistics based on PR processing result.

        Args:
            statistics: Statistics dictionary to update
            pr_data: PR processing result data
        """
        action = pr_data.get("action", "")

        statistics["total_prs_processed"] += 1

        if action == "approved":
            statistics["prs_auto_approved"] += 1
        elif action == "dependency_fix_applied":
            statistics["dependency_fixes_applied"] += 1

    async def _generate_dashboard_body(self, data: Dict[str, Any]) -> str:
        """
        Generate dashboard issue body from data.

        Args:
            data: Dashboard data

        Returns:
            Issue body markdown
        """
        # Generate human-readable report
        report = await self._generate_human_readable_report(data)

        # Embed structured data in HTML comment
        structured_data = json.dumps(data, indent=2)

        body = f"""{report}

---

<!-- DASHBOARD_DATA
{structured_data}
-->

<sub>This dashboard is automatically maintained by the Renovate PR Assistant. Last updated: {data.get('last_updated', 'unknown')}</sub>"""

        return body

    async def _generate_human_readable_report(self, data: Dict[str, Any]) -> str:
        """
        Generate human-readable dashboard report.

        Args:
            data: Dashboard data

        Returns:
            Markdown report
        """
        repo_name = data.get("repository", "Unknown Repository")
        open_prs = data.get("open_renovate_prs", [])
        stats = data.get("statistics", {})
        last_updated = data.get("last_updated", "unknown")

        # Format last updated time
        try:
            updated_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            updated_str = updated_dt.strftime("%Y-%m-%d %H:%M UTC")
        except:
            updated_str = last_updated

        report = f"""# 🤖 Renovate PRs Assistant Dashboard

## Repository: {repo_name}

### 📊 Summary

- **Open Renovate PRs:** {len(open_prs)}
- **Total PRs Processed:** {stats.get('total_prs_processed', 0)}
- **Auto-approved PRs:** {stats.get('prs_auto_approved', 0)}
- **Dependency Fixes Applied:** {stats.get('dependency_fixes_applied', 0)}
- **Currently Blocked:** {stats.get('blocked_prs', 0)}

### 🔄 Open Renovate PRs"""

        if open_prs:
            for pr in open_prs:
                status_emoji = self._get_status_emoji(pr.get("status", "unknown"))
                title = pr.get("title", "Unknown")
                number = pr.get("number", "?")
                url = pr.get("url", "#")
                status_reason = pr.get("status_reason", "unknown")

                report += f"\n- {status_emoji} [#{number}]({url}) {title}"

                if pr.get("status") == "blocked":
                    report += f" _(blocked: {status_reason})_"
                elif pr.get("status") == "waiting":
                    report += f" _(waiting: {status_reason})_"
        else:
            report += "\n\n✅ No open Renovate PRs found."

        report += """

### 📈 Recent Activity

The Renovate PR Assistant is actively monitoring this repository for Renovate PRs and will:

- ✅ **Auto-approve** PRs with passing checks
- 🔧 **Fix dependencies** when lock files need updates
- 🚫 **Block** PRs with failing checks or merge conflicts
- 📊 **Update this dashboard** with real-time status

### 🎯 Next Actions

"""

        # Add action items based on current state
        blocked_prs = [pr for pr in open_prs if pr.get("status") == "blocked"]
        waiting_prs = [pr for pr in open_prs if pr.get("status") == "waiting"]

        if blocked_prs:
            report += f"- **{len(blocked_prs)} PRs need attention** - review merge conflicts or failing checks\n"

        if waiting_prs:
            report += f"- **{len(waiting_prs)} PRs waiting** for checks to complete\n"

        if not open_prs:
            report += "- 🎉 All Renovate PRs are processed! Repository is up to date.\n"

        report += f"\n*Last updated: {updated_str}*"

        return report

    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for PR status."""
        status_emojis = {
            "ready": "✅",
            "waiting": "⏳",
            "blocked": "🚫",
            "error": "❌",
            "unknown": "❓"
        }
        return status_emojis.get(status, "❓")

    async def add_processed_pr_record(self, repo: Repository, pr_number: int,
                                    action: str, result: Dict[str, Any]) -> bool:
        """
        Add a record of a processed PR to the dashboard.

        Args:
            repo: Repository object
            pr_number: PR number
            action: Action taken
            result: Processing result

        Returns:
            True if successful
        """
        try:
            # Create PR processing record
            pr_record = {
                "pr_number": pr_number,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": result.get("success", True),
                "details": result
            }

            # Update dashboard with this record
            return await self.update_dashboard_issue(repo, pr_record)

        except Exception as e:
            logger.error("Failed to add processed PR record",
                        repo=repo.full_name,
                        pr_number=pr_number,
                        error=str(e))
            return False

    async def _find_dashboard_issues(self, repo: Repository) -> List[Issue]:
        """
        Find all dashboard issues in the repository.
        
        Args:
            repo: Repository object
            
        Returns:
            List of dashboard issues, sorted by creation date (oldest first)
        """
        await self.github_client._check_rate_limit()
        
        try:
            # Search for all open issues with our title
            issues = []
            for issue in repo.get_issues(state="open"):
                if issue.title == self.dashboard_title:
                    issues.append(issue)
            
            # Sort by creation date (oldest first)
            issues.sort(key=lambda x: x.created_at)
            
            logger.info("Found dashboard issues",
                       repo=repo.full_name,
                       count=len(issues))
            
            return issues
            
        except Exception as e:
            logger.error("Failed to find dashboard issues",
                        repo=repo.full_name,
                        error=str(e))
            return []

    async def _close_duplicate_dashboard_issues(self, repo: Repository, duplicate_issues: List[Issue]) -> None:
        """
        Close duplicate dashboard issues.
        
        Args:
            repo: Repository object
            duplicate_issues: List of issues to close
        """
        for issue in duplicate_issues:
            try:
                # Add comment explaining closure
                comment_body = (
                    "🤖 **Duplicate Dashboard Issue**\n\n"
                    "This issue is a duplicate of an existing Renovate PRs Assistant dashboard. "
                    "Closing to prevent noise and maintain a single source of truth.\n\n"
                    "The primary dashboard issue will be kept active for status updates."
                )
                
                issue.create_comment(comment_body)
                issue.edit(state="closed")
                
                logger.info("Closed duplicate dashboard issue",
                           repo=repo.full_name,
                           issue_number=issue.number)
                           
            except Exception as e:
                logger.error("Failed to close duplicate dashboard issue",
                            repo=repo.full_name,
                            issue_number=issue.number,
                            error=str(e))

    async def ensure_dashboard_issue(self, repo: Repository) -> Issue:
        """
        Ensure a single dashboard issue exists for the repository.
        
        This is a convenience method that ensures proper cleanup
        and prevents duplicate issues.
        
        Args:
            repo: Repository object
            
        Returns:
            Dashboard issue object
        """
        return await self.get_or_create_dashboard_issue(repo)
