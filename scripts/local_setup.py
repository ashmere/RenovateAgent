#!/usr/bin/env python3
"""
Local development setup script for Renovate PR Assistant.

This script helps set up local testing environment using GitHub CLI authentication
or guides you through creating a Personal Access Token.
"""

import os
import subprocess
import sys
from pathlib import Path


def get_github_token_from_cli():
    """Get GitHub token from gh CLI if available."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def create_env_file(token, org):
    """Create .env file for local development."""
    env_content = f"""# Local development configuration for Renovate PR Assistant
# This uses Personal Access Token instead of GitHub App

# GitHub configuration (PAT mode)
GITHUB_APP_ID=0
GITHUB_APP_PRIVATE_KEY_PATH=""
GITHUB_WEBHOOK_SECRET=dev-secret
GITHUB_PERSONAL_ACCESS_TOKEN={token}
GITHUB_ORGANIZATION={org}

# Server configuration
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Database (local SQLite)
DATABASE_URL=sqlite:///./renovate_agent_dev.db

# Logging
LOG_LEVEL=DEBUG
LOG_FORMAT=pretty

# Features (all enabled for testing)
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=["python", "typescript", "go"]
"""

    with open(".env", "w") as f:
        f.write(env_content)

    print("✅ Created .env file for local development")


def main():
    """Main setup function."""
    print("🚀 Renovate PR Assistant - Local Development Setup")
    print("=" * 50)

    # Check if we're in the right directory
    if not Path("src/renovate_agent").exists():
        print("❌ Please run this script from the project root directory")
        sys.exit(1)

    # Try to get token from gh CLI
    print("🔍 Checking for GitHub CLI authentication...")
    token = get_github_token_from_cli()

    if token:
        print("✅ Found GitHub CLI token!")
        print(f"   Token: {token[:10]}...")
    else:
        print("❌ No GitHub CLI token found.")
        print("\n📝 To set up GitHub CLI authentication:")
        print("   1. Run: gh auth login")
        print("   2. Follow the prompts")
        print("   3. Run this script again")
        print("\n🔗 Or create a Personal Access Token manually:")
        print("   1. Go to: https://github.com/settings/tokens")
        print("   2. Click 'Generate new token (classic)'")
        print("   3. Select scopes: repo, read:org, read:user")
        print("   4. Copy the token and run:")
        print("      export GITHUB_TOKEN=your_token_here")
        print("      python scripts/local_setup.py")

        # Check for manual token
        manual_token = os.getenv("GITHUB_TOKEN")
        if manual_token:
            token = manual_token
            print(f"\n✅ Using manually provided token: {token[:10]}...")
        else:
            sys.exit(1)

    # Get organization
    org = input("\n🏢 Enter your GitHub organization/username for testing: ").strip()
    if not org:
        print("❌ Organization is required")
        sys.exit(1)

    # Create .env file
    create_env_file(token, org)

    print("\n🎉 Setup complete!")
    print("\n📋 Next steps:")
    print("   1. Install dependencies: pip install -r requirements.txt")
    print("   2. Install pre-commit hooks: pre-commit install")
    print("   3. Run tests: pytest")
    print("   4. Start the server: python -m renovate_agent.main")
    print("\n🔗 Test webhook endpoint: http://localhost:8000/webhook")
    print("📊 Health check: http://localhost:8000/health")


if __name__ == "__main__":
    main()
