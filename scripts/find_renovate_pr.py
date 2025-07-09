#!/usr/bin/env python3
"""
Find an open unapproved Renovate PR for testing.

This script discovers test repositories and finds a suitable Renovate PR
that can be used for approval testing.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Now import the project modules
from renovate_agent.config import get_settings  # noqa: E402
from renovate_agent.github_client import GitHubClient  # noqa: E402


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
    fallback_repos = ["skyral-group/ee-sdlc", "ashmere/docgenai"]

    print(f"ℹ️  No test repositories configured, using fallbacks: " f"{fallback_repos}")
    return fallback_repos


async def check_pr_approval_status(client: GitHubClient, repo, pr) -> Tuple[bool, str]:
    """Check if a PR is already approved."""
    try:
        reviews = list(pr.get_reviews())

        # Check for any approving reviews
        approved_reviews = [r for r in reviews if r.state == "APPROVED"]
        if approved_reviews:
            user_login = approved_reviews[-1].user.login
            return True, f"Already approved by {user_login}"

        # Check for blocking reviews
        blocking_reviews = [
            r for r in reviews if r.state in ["REQUEST_CHANGES", "CHANGES_REQUESTED"]
        ]
        if blocking_reviews:
            user_login = blocking_reviews[-1].user.login
            return False, f"Has requested changes from {user_login}"

        return False, "No approvals"

    except Exception as e:
        return False, f"Could not check approval status: {e}"


async def check_pr_checks(client: GitHubClient, repo, pr) -> Tuple[bool, str]:
    """Check if PR has passing checks."""
    try:
        commit = pr.get_commits().reversed[0]
        check_runs = list(commit.get_check_runs())
        status_checks = list(commit.get_statuses())

        total_checks = len(check_runs) + len(status_checks)
        if total_checks == 0:
            return True, "No checks required"

        # Check run status
        failing_check_runs = [
            cr
            for cr in check_runs
            if cr.conclusion in ["failure", "cancelled", "timed_out"]
        ]
        pending_check_runs = [
            cr for cr in check_runs if cr.status in ["queued", "in_progress"]
        ]

        # Status check status
        failing_status_checks = [
            sc for sc in status_checks if sc.state in ["failure", "error"]
        ]
        pending_status_checks = [sc for sc in status_checks if sc.state == "pending"]

        if failing_check_runs or failing_status_checks:
            failed_count = len(failing_check_runs + failing_status_checks)
            return False, f"Has failing checks: {failed_count} failed"

        if pending_check_runs or pending_status_checks:
            pending_count = len(pending_check_runs + pending_status_checks)
            return False, f"Has pending checks: {pending_count} pending"

        return True, f"All {total_checks} checks passing"

    except Exception as e:
        return True, f"Could not check CI status: {e}"


async def find_suitable_renovate_pr(repo_name: str) -> Optional[Dict]:
    """Find a suitable Renovate PR for testing in the given repository."""
    settings = get_settings()
    client = GitHubClient(settings)

    try:
        # Get repository
        repo = await client.get_repo(repo_name)

        # Get all open PRs
        open_prs = list(repo.get_pulls(state="open"))

        renovate_prs = []

        for pr in open_prs:
            # Check if it's a Renovate PR
            is_renovate = await client.is_renovate_pr(pr)
            if not is_renovate:
                continue

            # Check approval status
            is_approved, approval_reason = await check_pr_approval_status(
                client, repo, pr
            )

            # Check CI status
            checks_passing, check_reason = await check_pr_checks(client, repo, pr)

            # Determine suitability
            suitable = not is_approved and checks_passing

            if suitable:
                reason = "Ready for approval"
            else:
                not_suitable_reason = approval_reason if is_approved else check_reason
                reason = f"Not suitable: {not_suitable_reason}"

            pr_info = {
                "repository": repo_name,
                "number": pr.number,
                "title": pr.title,
                "url": pr.html_url,
                "branch": pr.head.ref,
                "author": pr.user.login,
                "is_approved": is_approved,
                "approval_reason": approval_reason,
                "checks_passing": checks_passing,
                "check_reason": check_reason,
                "suitable_for_testing": suitable,
                "reason": reason,
            }

            renovate_prs.append(pr_info)

        suitable_prs = [pr for pr in renovate_prs if pr["suitable_for_testing"]]

        return {
            "repository": repo_name,
            "total_open_prs": len(open_prs),
            "renovate_prs": renovate_prs,
            "suitable_prs": suitable_prs,
        }

    except Exception as e:
        return {
            "repository": repo_name,
            "error": str(e),
            "total_open_prs": 0,
            "renovate_prs": [],
            "suitable_prs": [],
        }


async def main():
    """Main function to find suitable Renovate PRs."""
    # Check authentication
    github_pat = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    github_app_id = os.getenv("GITHUB_APP_ID")

    if not github_pat and not github_app_id:
        print("❌ GitHub authentication not configured", file=sys.stderr)
        print(
            "💡 Set GITHUB_PERSONAL_ACCESS_TOKEN or configure GitHub App",
            file=sys.stderr,
        )
        sys.exit(1)

    # Test GitHub connection first
    settings = get_settings()
    client = GitHubClient(settings)

    try:
        await client._authenticate()
    except Exception as e:
        print(f"❌ GitHub authentication failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Get test repositories
    test_repos = get_test_repositories()

    all_results = []
    suitable_prs = []

    for repo_name in test_repos:
        print(f"🔍 Checking {repo_name}...", file=sys.stderr)
        result = await find_suitable_renovate_pr(repo_name)
        all_results.append(result)

        if "error" in result:
            print(f"❌ Error with {repo_name}: {result['error']}", file=sys.stderr)
            continue

        suitable_prs.extend(result["suitable_prs"])

        renovate_count = len(result["renovate_prs"])
        suitable_count = len(result["suitable_prs"])
        print(
            f"   Found {renovate_count} Renovate PRs " f"({suitable_count} suitable)",
            file=sys.stderr,
        )

    # Output results
    output = {
        "timestamp": "2025-07-09T16:30:00Z",  # Current time
        "test_repositories": test_repos,
        "total_suitable_prs": len(suitable_prs),
        "results": all_results,
    }

    # Print JSON to stdout for consumption by shell scripts
    print(json.dumps(output, indent=2))

    # Print summary to stderr for human consumption
    if suitable_prs:
        print(
            f"\n✅ Found {len(suitable_prs)} suitable PRs for testing:", file=sys.stderr
        )
        for pr in suitable_prs:
            repo_and_number = f"{pr['repository']}#{pr['number']}"
            print(f"   - {repo_and_number}: {pr['title']}", file=sys.stderr)
        sys.exit(0)
    else:
        repo_count = len(test_repos)
        print(
            f"\n❌ No suitable Renovate PRs found in {repo_count} repositories",
            file=sys.stderr,
        )
        print("💡 Suitable PRs must be:", file=sys.stderr)
        print("   - Created by Renovate", file=sys.stderr)
        print("   - Not already approved", file=sys.stderr)
        print("   - Have passing CI checks", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
