#!/usr/bin/env python3
"""
Test issue creation for Renovate PRs Assistant dashboard.

This script will create actual dashboard issues in your repositories.
"""

import os
import sys
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
        print("❌ GITHUB_TEST_REPOSITORIES environment variable not set")
        print("💡 Set: export GITHUB_TEST_REPOSITORIES=org/repo1,org/repo2")
        return None
    
    repositories = []
    for repo in test_repos:
        repo = repo.strip()
        if "/" not in repo:
            print(f"❌ Repository '{repo}' must be in format 'org/repo'")
            return None
        repositories.append(repo)
    
    return repositories


async def test_dashboard_creation():
    """Test creating dashboard issues in target repositories."""
    print("🎯 Testing Dashboard Issue Creation")
    print("=" * 50)
    
    target_repos = get_target_repositories()
    if not target_repos:
        return []
    
    settings = get_settings()
    client = GitHubClient(settings)
    
    # Authenticate
    await client._authenticate()
    
    results = []
    
    for repo_name in target_repos:
        try:
            print(f"\n📋 Processing {repo_name}...")
            repo = await client.get_repo(repo_name)
            
            # Initialize issue manager
            issue_manager = IssueStateManager(client, repo)
            
            # Create or update dashboard issue
            print("   🔧 Creating/updating dashboard issue...")
            dashboard_issue = await issue_manager.ensure_dashboard_issue()
            
            if dashboard_issue:
                print("   ✅ Dashboard issue created/updated!")
                print(f"   📝 Issue #{dashboard_issue.number}: "
                      f"{dashboard_issue.title}")
                print(f"   🔗 URL: {dashboard_issue.html_url}")
                
                # Get some real repository stats
                open_prs = list(repo.get_pulls(state='open'))
                # Last 10 closed
                closed_prs = list(repo.get_pulls(state='closed'))[:10]
                
                # Update with real stats
                renovate_prs = [
                    pr for pr in open_prs 
                    if ('renovate' in pr.user.login.lower() or 
                        'dependabot' in pr.user.login.lower())
                ]
                stats = {
                    'total_open_prs': len(open_prs),
                    'renovate_prs': len(renovate_prs),
                    'last_updated': '2025-01-08T10:50:00Z',
                    'recent_activity': (f"Found {len(open_prs)} open PRs, "
                                      f"{len(closed_prs)} recent closed PRs")
                }
                
                await issue_manager.update_dashboard_stats(stats)
                print("   📊 Dashboard updated with real repository stats")
                
                results.append({
                    'repo': repo_name,
                    'issue_number': dashboard_issue.number,
                    'issue_url': dashboard_issue.html_url,
                    'stats': stats
                })
            else:
                print(f"   ❌ Failed to create dashboard issue")
                
        except Exception as e:
            print(f"   ❌ Error processing {repo_name}: {e}")
            import traceback
            traceback.print_exc()
    
    return results


async def test_pr_analysis():
    """Test analyzing existing PRs in repositories."""
    print("\n🔍 Analyzing Existing PRs")
    print("=" * 30)
    
    settings = get_settings()
    client = GitHubClient(settings)
    
    # Authenticate
    await client._authenticate()
    
    target_repos = get_target_repositories()
    if not target_repos:
        return
    
    for repo_name in target_repos:
        try:
            print(f"\n📋 Analyzing PRs in {repo_name}...")
            repo = await client.get_repo(repo_name)
            
            # Get open PRs
            open_prs = list(repo.get_pulls(state='open'))
            print(f"   📊 Found {len(open_prs)} open PRs")
            
            for pr in open_prs[:3]:  # Analyze first 3 PRs
                print(f"\n   🔍 PR #{pr.number}: {pr.title[:50]}...")
                print(f"      Author: {pr.user.login}")
                print(f"      State: {pr.state}")
                print(f"      Created: {pr.created_at}")
                
                # Check if it's a dependency PR
                is_renovate = await client.is_renovate_pr(pr)
                is_dependabot = 'dependabot' in pr.user.login.lower()
                
                if is_renovate:
                    print(f"      🤖 Renovate PR - would be processed!")
                elif is_dependabot:
                    print(f"      🤖 Dependabot PR - would be processed!")
                else:
                    print(f"      👤 Human PR - would be ignored")
            
        except Exception as e:
            print(f"   ❌ Error analyzing {repo_name}: {e}")


async def main():
    """Main test function."""
    print("🚀 Renovate PR Assistant - Live Repository Testing")
    print("This will create REAL issues in your repositories!")
    print("=" * 60)
    
    # Confirm with user
    response = input("Do you want to create dashboard issues in your repositories? (y/N): ")
    if response.lower() != 'y':
        print("❌ Cancelled by user")
        return False
    
    try:
        # Test 1: Create dashboard issues
        dashboard_results = await test_dashboard_creation()
        
        # Test 2: Analyze existing PRs
        await test_pr_analysis()
        
        print(f"\n🎉 Live testing complete!")
        
        if dashboard_results:
            print(f"\n📋 Dashboard Issues Created:")
            for result in dashboard_results:
                print(f"   ✅ {result['repo']}")
                print(f"      Issue: #{result['issue_number']}")
                print(f"      URL: {result['issue_url']}")
                print(f"      Stats: {result['stats']['total_open_prs']} open PRs, {result['stats']['renovate_prs']} dependency PRs")
        
        print(f"\n💡 Next steps:")
        print(f"   1. Check the issues created in your repositories")
        print(f"   2. Create a test PR to see the system in action")
        print(f"   3. Configure real webhooks for live processing")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import asyncio
    
    # Check environment
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        print("❌ GITHUB_PERSONAL_ACCESS_TOKEN not set")
        sys.exit(1)
    
    if not os.getenv("GITHUB_ORGANIZATION"):
        print("❌ GITHUB_ORGANIZATION not set")
        print("💡 Set: export GITHUB_ORGANIZATION=your-org-name")
        sys.exit(1)
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 
