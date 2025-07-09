#!/usr/bin/env python3
"""
Local development setup script for Renovate PR Assistant.

This script helps set up local testing environment using GitHub CLI
authentication or guides you through creating a Personal Access Token.

Supports both interactive and non-interactive modes:
- Interactive: Prompts for configuration choices
- Non-interactive: Automatically updates existing .env safely
"""

import argparse
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


def validate_github_access(token, org):
    """Validate GitHub token and organization access."""
    try:
        import requests

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Test basic authentication
        response = requests.get("https://api.github.com/user", headers=headers)
        if response.status_code != 200:
            return False, f"Token validation failed: {response.status_code}"

        user_data = response.json()
        username = user_data.get("login")

        # Test organization access
        org_response = requests.get(
            f"https://api.github.com/orgs/{org}", headers=headers
        )
        if org_response.status_code == 200:
            msg = f"✅ Access confirmed for org '{org}' as user '{username}'"
            return (True, msg)
        elif org_response.status_code == 404:
            # Might be a user account, check user repos
            user_response = requests.get(
                f"https://api.github.com/users/{org}", headers=headers
            )
            if user_response.status_code == 200:
                msg = f"✅ Access confirmed for user '{org}' as '{username}'"
                return (True, msg)
            else:
                return (
                    False,
                    f"Organization/user '{org}' not found or not accessible",
                )
        else:
            return False, f"Cannot access '{org}': {org_response.status_code}"

    except ImportError:
        return (
            True,
            "⚠️  Cannot validate access (requests not installed), proceeding anyway",
        )
    except Exception as e:
        return False, f"Validation error: {e}"


def get_repository_suggestions(org):
    """Get repository suggestions based on organization."""
    suggestions = {
        "skyral-group": [
            "skyral-group/ee-sdlc",
            "skyral-group/skyral-ee-security-sandbox",
        ],
        "ashmere": ["ashmere/RenovateAgent"],
    }

    return suggestions.get(org, [f"{org}/example-repo"])


def read_existing_env():
    """Read existing .env file and extract key values."""
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Remove quotes if present
                    value = value.strip("\"'")
                    env_vars[key] = value
    return env_vars


def create_or_update_env_file(token, org, test_repos=None, update_mode=False):
    """Create new .env file or update existing one preserving sensitive data."""

    # Read existing values if updating
    existing_vars = {}
    if update_mode and os.path.exists(".env"):
        existing_vars = read_existing_env()
        print("📄 Found existing .env file, preserving sensitive data...")

        # Use existing values if available
        token = existing_vars.get("GITHUB_PERSONAL_ACCESS_TOKEN", token)
        org = existing_vars.get("GITHUB_ORGANIZATION", org)
        existing_repos = existing_vars.get("GITHUB_TEST_REPOSITORIES", "")
        if existing_repos and not test_repos:
            test_repos = existing_repos

    # Get repository suggestions if none provided
    if not test_repos:
        suggested_repos = get_repository_suggestions(org)
        test_repos = ",".join(suggested_repos)

    # Generate current .env format with only supported variables
    env_content = f"""# RenovateAgent Configuration
# Generated/Updated by local_setup.py on {os.popen('date +%Y-%m-%d').read().strip()}

# GitHub Authentication (choose one)
GITHUB_APP_ID=0
GITHUB_PERSONAL_ACCESS_TOKEN={token}
GITHUB_APP_PRIVATE_KEY_PATH=
GITHUB_WEBHOOK_SECRET=dev-secret
GITHUB_ORGANIZATION={org}
GITHUB_API_URL=https://api.github.com

# Polling Mode (Phase 2 Optimized for Local Testing)
ENABLE_POLLING=true
POLLING_INTERVAL_SECONDS=120
POLLING_MAX_INTERVAL_SECONDS=600
POLLING_ADAPTIVE=true
POLLING_CONCURRENT_REPOS=5

# Repository Settings
GITHUB_REPOSITORY_ALLOWLIST=
GITHUB_TEST_REPOSITORIES={test_repos}
IGNORE_ARCHIVED_REPOSITORIES=true

# Dependency Fixing
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=python,typescript,go
CLONE_TIMEOUT=300
DEPENDENCY_UPDATE_TIMEOUT=600

# Dashboard
DASHBOARD_ISSUE_TITLE="Renovate PRs Assistant Dashboard"
UPDATE_DASHBOARD_ON_EVENTS=true
DASHBOARD_CREATION_MODE=renovate-only

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Logging
LOG_LEVEL=INFO
"""

    with open(".env", "w") as f:
        f.write(env_content)

    action = "Updated" if update_mode else "Created"
    print(f"✅ {action} .env file for local development")
    print("📋 Configuration summary:")
    print(f"   Organization: {org}")
    print(f"   Test repositories: {test_repos}")
    print(f"   Token: {token[:10]}...")
    if update_mode:
        print("   🔒 Preserved existing sensitive data")
        print("   🔄 Updated to current configuration format")


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        subprocess.run(["poetry", "--version"], capture_output=True, check=True)
        print("✅ Poetry is installed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Poetry not found. Install it from: https://python-poetry.org/docs/")
        return False

    try:
        subprocess.run(["direnv", "--version"], capture_output=True, check=True)
        print("✅ direnv is installed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  direnv not found. Install it for automatic environment loading:")
        print("   brew install direnv  # on macOS")
        print("   apt install direnv   # on Ubuntu")

    return True


def main():
    """Main setup function."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Setup local development environment for RenovateAgent"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode (auto-updates existing .env safely)",
    )
    args = parser.parse_args()

    print("🚀 Renovate PR Assistant - Local Development Setup")
    if args.non_interactive:
        print("🤖 Running in non-interactive mode")
    print("=" * 50)

    # Check if we're in the right directory
    if not Path("src/renovate_agent").exists():
        print("❌ Please run this script from the project root directory")
        sys.exit(1)

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Check if .env already exists
    env_exists = os.path.exists(".env")
    update_mode = False

    if env_exists:
        print("\n📄 Existing .env file detected")

        if args.non_interactive:
            # Non-interactive mode: always use safe update mode
            update_mode = True
            print("🔄 Non-interactive mode: Using safe update mode")
            print("   Will preserve existing sensitive data")
        else:
            # Interactive mode: ask user
            update_choice = (
                input(
                    "Update existing .env (preserves token/org) or create fresh? "
                    "[U]pdate/[F]resh: "
                )
                .strip()
                .lower()
            )
            update_mode = update_choice in ["", "u", "update"]

            if update_mode:
                print("🔄 Update mode: Will preserve existing sensitive data")
            else:
                print("🆕 Fresh mode: Will create new configuration")
    elif args.non_interactive:
        print("\n🤖 Non-interactive mode with no existing .env")
        print("❌ Cannot run non-interactively without existing configuration")
        print("   Please run interactively first: python scripts/local_setup.py")
        sys.exit(1)

    # Try to get token from existing .env or CLI
    token = None
    org = None

    test_repos = None
    if update_mode:
        existing_vars = read_existing_env()
        token = existing_vars.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        org = existing_vars.get("GITHUB_ORGANIZATION")
        test_repos = existing_vars.get("GITHUB_TARGET_REPOSITORIES")

        if token and org:
            print("✅ Found existing token and organization")
            print(f"   Token: {token[:10]}...")
            print(f"   Organization: {org}")
            if test_repos:
                print(f"   Test repositories: {test_repos}")
        else:
            print("⚠️  Incomplete existing config, will prompt for missing data")
            update_mode = False  # Fall back to fresh setup

    if not token:
        print("\n🔍 Checking for GitHub CLI authentication...")
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
            print("   3. Select scopes: repo, read:org, read:user, write:issues")
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

    # Get organization if not from existing config
    if not org:
        if args.non_interactive:
            print("❌ No organization found in existing .env")
            print("   Cannot run non-interactively without organization")
            sys.exit(1)

        print("\n🏢 Organization Setup")
        org_prompt = "Enter your GitHub organization/username for testing: "
        org = input(org_prompt).strip()
        if not org:
            print("❌ Organization is required")
            sys.exit(1)

    # Validate GitHub access
    print(f"\n🔒 Validating access to '{org}'...")
    is_valid, message = validate_github_access(token, org)
    print(f"   {message}")

    if not is_valid:
        print("❌ Access validation failed.")
        print("   Please check your token permissions and organization name.")
        sys.exit(1)

    # Get test repositories if not from existing config
    if not test_repos and not update_mode:
        if args.non_interactive:
            # Non-interactive mode without existing test repos
            suggested_repos = get_repository_suggestions(org)
            test_repos = ",".join(suggested_repos)
            print(f"\n📚 Non-interactive mode: Using suggested repositories")
            print(f"   Test repositories: {test_repos}")
        else:
            print("\n📚 Test Repository Setup")
            suggested_repos = get_repository_suggestions(org)
            print("Suggested test repositories:")
            for repo in suggested_repos:
                print(f"   - {repo}")

            repo_prompt = "\nUse suggested repositories? [Y/n]: "
            use_suggested = input(repo_prompt).strip().lower()
            if use_suggested in ["", "y", "yes"]:
                test_repos = ",".join(suggested_repos)
            else:
                print("Enter test repositories (format: org/repo1,org/repo2):")
                test_repos = input("Test repositories: ").strip()
                if not test_repos:
                    test_repos = ",".join(suggested_repos)
                    print(f"Using default: {test_repos}")

    # Create or update .env file
    action = "Updating" if update_mode else "Creating"
    print(f"\n📄 {action} .env file...")
    create_or_update_env_file(token, org, test_repos, update_mode)

    print("\n🎉 Setup complete!")
    print("\n📋 Next steps:")
    print("   1. Install dependencies: poetry install")
    print("   2. Install pre-commit hooks: poetry run pre-commit install")
    print("   3. Run tests: poetry run pytest")
    print("   4. Test GitHub connection:")
    print("      poetry run python scripts/test_github_connection.py")
    print("   5. Test target repositories:")
    print("      poetry run python scripts/test_target_repos.py")
    print("   6. Start the server:")
    print("      poetry run python -m renovate_agent.main")
    print("   7. Run end-to-end tests: ./test-runner.sh")
    print("\n🔗 Useful endpoints:")
    print("   • Health check: http://localhost:8000/health")
    print("   • API docs: http://localhost:8000/docs")
    print("   • Webhook endpoint: http://localhost:8000/webhooks/github")
    print("\n📖 For more information, see LOCAL_TESTING.md")


if __name__ == "__main__":
    main()
