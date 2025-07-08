#!/usr/bin/env python3
"""
Test GitHub connection for local development.

This script tests if your GitHub authentication is working correctly.
"""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from renovate_agent.config import get_settings
from renovate_agent.github_client import GitHubClient


async def test_github_connection():
    """Test GitHub connection and basic API access."""
    print("🔍 Testing GitHub connection...")
    
    try:
        # Get settings (will use PAT if configured)
        settings = get_settings()
        
        print(f"📋 Configuration:")
        print(f"   Organization: {settings.github_organization}")
        print(f"   Development mode: {settings.is_development_mode}")
        
        if not settings.is_development_mode:
            print("❌ Not in development mode. Please set GITHUB_PERSONAL_ACCESS_TOKEN")
            return False
            
        # Create GitHub client
        client = GitHubClient(settings)
        
        # Test authentication
        await client._authenticate()
        print("✅ GitHub authentication successful!")
        
        # Test basic API access
        github_instance = await client._get_github_instance()
        user = github_instance.get_user()
        print(f"✅ Connected as: {user.login}")
        
        # Test organization access
        try:
            org = github_instance.get_organization(settings.github_organization)
            print(f"✅ Organization access: {org.name}")
            
            # List a few repositories
            repos = list(org.get_repos()[:5])
            print(f"✅ Found {len(repos)} repositories")
            for repo in repos:
                print(f"   - {repo.name}")
                
        except Exception as e:
            # Might be a user account, not an org
            print(f"ℹ️  Treating as user account: {e}")
            user_repos = list(github_instance.get_user().get_repos()[:5])
            print(f"✅ Found {len(user_repos)} user repositories")
            for repo in user_repos:
                print(f"   - {repo.name}")
        
        print("\n🎉 GitHub connection test successful!")
        return True
        
    except Exception as e:
        print(f"❌ GitHub connection failed: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    
    print("🚀 Renovate PR Assistant - GitHub Connection Test")
    print("=" * 50)
    
    # Check if we have the required environment
    if not os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"):
        print("❌ GITHUB_PERSONAL_ACCESS_TOKEN not set")
        print("\n💡 Run the setup script first:")
        print("   python scripts/local_setup.py")
        sys.exit(1)
    
    success = asyncio.run(test_github_connection())
    sys.exit(0 if success else 1) 
