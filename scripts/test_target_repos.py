#!/usr/bin/env python3
"""
Test Renovate PR Assistant on specific target repositories.

This script tests the system on configured target repositories.
Uses environment variables for repository configuration.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from renovate_agent.config import get_settings
from renovate_agent.github_client import GitHubClient
from renovate_agent.pr_processor import PRProcessor


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


async def test_repository_access():
    """Test access to target repositories."""
    print("🏢 Testing Repository Access")
    print("=" * 50)
    
    target_repos = get_target_repositories()
    if not target_repos:
        return []
    
    settings = get_settings()
    client = GitHubClient(settings)
    
    # Authenticate
    await client._authenticate()
    
    accessible_repos = []
    
    for repo_name in target_repos:
        try:
            print(f"\n🔍 Testing access to {repo_name}...")
            repo = await client.get_repo(repo_name)
            
            print(f"✅ Repository accessible: {repo.name}")
            print(f"   Description: {repo.description or 'No description'}")
            print(f"   Language: {repo.language or 'Not specified'}")
            print(f"   Private: {repo.private}")
            print(f"   Has Issues: {repo.has_issues}")
            print(f"   Open PRs: {repo.get_pulls(state='open').totalCount}")
            
            accessible_repos.append(repo_name)
            
        except Exception as e:
            print(f"❌ Cannot access {repo_name}: {e}")
    
    return accessible_repos


async def test_pr_processing():
    """Test PR processing capabilities on target repositories."""
    print("\n🔄 Testing PR Processing Capabilities")
    print("=" * 40)
    
    settings = get_settings()
    client = GitHubClient(settings)
    pr_processor = PRProcessor(client, settings)
    
    accessible_repos = await test_repository_access()
    
    for repo_name in accessible_repos:
        try:
            print(f"\n📋 Analyzing PRs in {repo_name}...")
            repo = await client.get_repo(repo_name)
            
            # Get recent PRs
            prs = list(repo.get_pulls(state='all', sort='updated')[:5])
            print(f"   Found {len(prs)} recent PRs")
            
            for pr in prs:
                print(f"   - PR #{pr.number}: {pr.title[:50]}...")
                print(f"     State: {pr.state}, Author: {pr.user.login}")
                
                # Test if it's a Renovate PR
                is_renovate = await client.is_renovate_pr(pr)
                if is_renovate:
                    print(f"     🤖 This is a Renovate PR!")
                    
                    # Test check status analysis
                    try:
                        status = await pr_processor._get_check_status(repo, pr)
                        print(f"     ✅ Check status: {status}")
                    except Exception as e:
                        print(f"     ⚠️  Check status error: {e}")
                
        except Exception as e:
            print(f"❌ Error processing {repo_name}: {e}")


async def test_dependency_detection():
    """Test dependency file detection in target repositories."""
    print("\n📦 Testing Dependency File Detection")
    print("=" * 40)
    
    settings = get_settings()
    client = GitHubClient(settings)
    
    accessible_repos = await test_repository_access()
    
    for repo_name in accessible_repos:
        try:
            print(f"\n🔍 Checking dependency files in {repo_name}...")
            repo = await client.get_repo(repo_name)
            
            # Check for various dependency files
            dependency_files = [
                "pyproject.toml", "poetry.lock", "requirements.txt",  # Python
                "package.json", "package-lock.json", "yarn.lock",     # Node.js
                "go.mod", "go.sum"                                     # Go
            ]
            
            found_files = []
            for file_path in dependency_files:
                try:
                    file_content = repo.get_contents(file_path)
                    found_files.append(file_path)
                    print(f"   ✅ Found: {file_path}")
                except:
                    pass
            
            if found_files:
                print(f"   📋 Total dependency files: {len(found_files)}")
                
                # Determine language and fixer
                from renovate_agent.dependency_fixer.factory import DependencyFixerFactory
                factory = DependencyFixerFactory(settings)
                
                # Mock repository data for language detection
                mock_repo_data = {
                    'files': found_files,
                    'language': repo.language
                }
                
                fixer = factory.get_fixer(mock_repo_data)
                if fixer:
                    print(f"   🔧 Recommended fixer: {fixer.__class__.__name__}")
                else:
                    print(f"   ⚠️  No fixer available for detected files")
            else:
                print(f"   ℹ️  No dependency files found")
                
        except Exception as e:
            print(f"❌ Error checking {repo_name}: {e}")


async def main():
    """Main test function."""
    print("🚀 Renovate PR Assistant - Target Repository Testing")
    
    target_repos = get_target_repositories()
    if not target_repos:
        return False
    
    print("Target Repositories:")
    for repo in target_repos:
        print(f"  - {repo}")
    print("=" * 60)
    
    try:
        # Test 1: Repository Access
        accessible_repos = await test_repository_access()
        
        if not accessible_repos:
            print("\n❌ No repositories accessible. Check permissions.")
            return False
        
        # Test 2: PR Processing
        await test_pr_processing()
        
        # Test 3: Dependency Detection  
        await test_dependency_detection()
        
        print(f"\n🎉 Testing complete!")
        print(f"✅ Accessible repositories: {len(accessible_repos)}")
        print(f"🔧 Ready for Renovate PR processing!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    
    # Check environment
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        print("❌ GITHUB_PERSONAL_ACCESS_TOKEN not set")
        print("💡 Set the environment variable and try again")
        sys.exit(1)
    
    if not os.getenv("GITHUB_ORGANIZATION"):
        print("❌ GITHUB_ORGANIZATION not set")
        print("💡 Set: export GITHUB_ORGANIZATION=your-org-name")
        sys.exit(1)
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 
