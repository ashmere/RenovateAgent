#!/usr/bin/env python3
"""
Test improved Renovate PR detection and dashboard update.

This script tests the new flexible Renovate detection logic against actual
repositories to ensure it correctly identifies Renovate PRs.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from renovate_agent.config import get_settings
from renovate_agent.github_client import GitHubClient
from renovate_agent.issue_manager import IssueStateManager


def get_target_repositories():
    """Get target repositories from environment variables."""
    test_repos = os.getenv("GITHUB_TEST_REPOSITORIES", "").split(",")
    if not test_repos or not test_repos[0].strip():
        # Fallback for current testing
        return ["ashmere/docgenai"]
    
    repositories = []
    for repo in test_repos:
        repo = repo.strip()
        if "/" not in repo:
            print(f"❌ Repository '{repo}' must be in format 'org/repo'")
            return None
        repositories.append(repo)
    
    return repositories


async def test_renovate_detection():
    """Test Renovate PR detection on target repositories."""
    print("🔍 Testing Renovate PR Detection")
    print("=" * 50)
    
    target_repos = get_target_repositories()
    if not target_repos:
        return False
    
    settings = get_settings()
    client = GitHubClient(settings)
    
    # Authenticate
    await client._authenticate()
    
    for repo_name in target_repos:
        print(f"\n📁 Testing repository: {repo_name}")
        
        try:
            # Get repository
            repo = await client.get_repo(repo_name)
            
            # Get all open PRs
            open_prs = list(repo.get_pulls(state="open"))
            print(f"   Total open PRs: {len(open_prs)}")
            
            # Test Renovate detection
            renovate_prs = []
            for pr in open_prs:
                is_renovate = await client.is_renovate_pr(pr)
                if is_renovate:
                    renovate_prs.append(pr)
                    print(f"   ✅ Renovate PR #{pr.number}: {pr.title}")
                    print(f"      User: {pr.user.login} ({pr.user.type})")
                    print(f"      Branch: {pr.head.ref}")
                else:
                    print(f"   ⚪ Non-Renovate PR #{pr.number}: {pr.title}")
                    print(f"      User: {pr.user.login} ({pr.user.type})")
            
            print(f"\n   📊 Found {len(renovate_prs)} Renovate PRs out of {len(open_prs)} total")
            
        except Exception as e:
            print(f"   ❌ Error testing {repo_name}: {e}")
            return False
    
    return True


async def test_dashboard_update():
    """Test dashboard update with correct Renovate PR data."""
    print("\n\n🎯 Testing Dashboard Update")
    print("=" * 50)
    
    target_repos = get_target_repositories()
    if not target_repos:
        return False
    
    settings = get_settings()
    client = GitHubClient(settings)
    issue_manager = IssueStateManager(client, settings)
    
    # Authenticate
    await client._authenticate()
    
    for repo_name in target_repos:
        print(f"\n📁 Updating dashboard for: {repo_name}")
        
        try:
            # Get repository
            repo = await client.get_repo(repo_name)
            
            # Update dashboard
            success = await issue_manager.update_dashboard_issue(repo)
            
            if success:
                print(f"   ✅ Dashboard updated successfully")
                
                # Get the dashboard issue to show the URL
                dashboard_issue = await issue_manager.get_or_create_dashboard_issue(repo)
                print(f"   🔗 Dashboard URL: {dashboard_issue.html_url}")
            else:
                print(f"   ❌ Dashboard update failed")
                
        except Exception as e:
            print(f"   ❌ Error updating dashboard for {repo_name}: {e}")
            return False
    
    return True


async def main():
    """Main test function."""
    print("🚀 Renovate PR Assistant - Renovate Detection & Dashboard Test")
    print("=" * 65)
    
    # Check environment
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") and not os.getenv("GITHUB_APP_ID"):
        print("❌ GitHub authentication not configured")
        print("💡 Set GITHUB_PERSONAL_ACCESS_TOKEN or GITHUB_APP_ID")
        return False
    
    if not os.getenv("GITHUB_ORGANIZATION"):
        print("❌ GITHUB_ORGANIZATION not set")
        print("💡 Set: export GITHUB_ORGANIZATION=your-org-name")
        return False
    
    # Run tests
    try:
        detection_success = await test_renovate_detection()
        
        if detection_success:
            dashboard_success = await test_dashboard_update()
            
            if dashboard_success:
                print("\n🎉 All tests passed!")
                print("✅ Renovate detection working correctly")
                print("✅ Dashboard update successful")
                return True
            else:
                print("\n❌ Dashboard update tests failed")
                return False
        else:
            print("\n❌ Renovate detection tests failed")
            return False
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(main()) 
