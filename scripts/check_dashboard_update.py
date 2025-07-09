#!/usr/bin/env python3
"""
Check if dashboard issues were updated properly.

This script verifies that the dashboard issues contain the expected
information after a test run.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Now import the project modules
from renovate_agent.config import get_settings  # noqa: E402
from renovate_agent.github_client import GitHubClient  # noqa: E402
from renovate_agent.issue_manager import IssueStateManager  # noqa: E402


async def check_dashboard_for_repo(repo_name: str) -> Dict:
    """Check the dashboard issue for a specific repository."""
    settings = get_settings()
    client = GitHubClient(settings)
    issue_manager = IssueStateManager(client, settings)

    try:
        # Get repository
        repo = await client.get_repo(repo_name)

        # Find the dashboard issue
        dashboard_issue = await issue_manager.get_or_create_dashboard_issue(repo)

        if not dashboard_issue:
            return {
                "repository": repo_name,
                "error": "No dashboard issue found",
                "dashboard_url": None,
                "last_updated": None,
                "contains_recent_activity": False,
            }

        # Check when it was last updated
        last_updated = dashboard_issue.updated_at

        # Check if it was updated recently (within last hour)
        # Use timezone-aware datetime for comparison
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recently_updated = last_updated > one_hour_ago

        # Check content for recent activity
        body = dashboard_issue.body or ""

        # Look for common indicators of recent activity
        recent_indicators = [
            "ago)",  # timestamps like "(2 minutes ago)"
            "✅",  # approval checkmarks
            "🔄",  # processing indicators
            "Updated:",  # update timestamps
            str(datetime.now(timezone.utc).year),  # current year
        ]

        contains_recent_activity = any(
            indicator in body for indicator in recent_indicators
        )

        # Count PR entries
        pr_entries = body.count("PR #") if body else 0

        return {
            "repository": repo_name,
            "dashboard_url": dashboard_issue.html_url,
            "dashboard_number": dashboard_issue.number,
            "last_updated": last_updated.isoformat(),
            "recently_updated": recently_updated,
            "contains_recent_activity": contains_recent_activity,
            "pr_entries_count": pr_entries,
            "body_length": len(body),
            "has_content": bool(body and body.strip()),
        }

    except Exception as e:
        return {
            "repository": repo_name,
            "error": str(e),
            "dashboard_url": None,
            "last_updated": None,
            "recently_updated": False,
            "contains_recent_activity": False,
        }


def get_test_repositories() -> List[str]:
    """Get test repositories from environment variables."""
    # Try multiple environment variable sources
    repo_sources = [
        "POLLING_REPOSITORIES",
        "GITHUB_TEST_REPOSITORIES",
        "GITHUB_TARGET_REPOSITORIES",
    ]

    for source in repo_sources:
        test_repos = os.getenv(source, "").strip()
        if test_repos:
            repos = [repo.strip() for repo in test_repos.split(",") if repo.strip()]
            if repos:
                return repos

    # Fallback repos if none configured
    return ["skyral-group/ee-sdlc"]


async def main():
    """Main function to check dashboard updates."""
    # Check authentication
    github_pat = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    github_app_id = os.getenv("GITHUB_APP_ID")

    if not github_pat and not github_app_id:
        print("❌ GitHub authentication not configured", file=sys.stderr)
        sys.exit(1)

    # Get test repositories
    test_repos = get_test_repositories()

    # Test GitHub connection
    settings = get_settings()
    client = GitHubClient(settings)

    try:
        await client._authenticate()
    except Exception as e:
        print(f"❌ GitHub authentication failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Check each repository's dashboard
    results = []

    for repo_name in test_repos:
        print(f"🔍 Checking dashboard for {repo_name}...", file=sys.stderr)
        result = await check_dashboard_for_repo(repo_name)
        results.append(result)

        if "error" in result:
            print(f"❌ Error: {result['error']}", file=sys.stderr)
        else:
            print(f"✅ Dashboard found: {result['dashboard_url']}", file=sys.stderr)
            print(f"   Last updated: {result['last_updated']}", file=sys.stderr)
            print(f"   Recently updated: {result['recently_updated']}", file=sys.stderr)
            recent_activity = result["contains_recent_activity"]
            print(f"   Has recent activity: {recent_activity}", file=sys.stderr)
            print(f"   PR entries: {result['pr_entries_count']}", file=sys.stderr)

    # Output results as JSON
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_repositories": test_repos,
        "results": results,
    }

    print(json.dumps(output, indent=2))

    # Determine exit code based on results
    any_recently_updated = any(r.get("recently_updated", False) for r in results)
    any_errors = any("error" in r for r in results)

    if any_errors:
        print("\n❌ Some dashboard checks failed", file=sys.stderr)
        sys.exit(1)
    elif any_recently_updated:
        print("\n✅ Found recently updated dashboards", file=sys.stderr)
        sys.exit(0)
    else:
        print("\n⚠️  No recently updated dashboards found", file=sys.stderr)
        sys.exit(2)  # Different exit code for "no recent updates"


if __name__ == "__main__":
    asyncio.run(main())
