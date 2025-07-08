#!/usr/bin/env python3
"""
Test webhook processing for Renovate PR Assistant.

This script sends properly formatted GitHub webhook events to test the system.
Uses environment variables for repository configuration.
"""

import os
import sys

import requests


def get_test_repositories():
    """Get test repositories from environment variables."""
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

        org_name, repo_name = repo.split("/", 1)
        repositories.append({"full_name": repo, "name": repo_name, "org": org_name})

    return repositories


def test_ping_webhook():
    """Test ping webhook."""
    print("🔔 Testing ping webhook...")

    test_repos = get_test_repositories()
    if not test_repos:
        return False

    # Use first repository for ping test
    repo = test_repos[0]

    payload = {
        "zen": "Keep it logically awesome.",
        "hook_id": 12345,
        "repository": {
            "full_name": repo["full_name"],
            "name": repo["name"],
            "owner": {"login": repo["org"]},
        },
    }

    response = requests.post(
        "http://localhost:8000/webhooks/github",
        json=payload,
        headers={"X-GitHub-Event": "ping", "User-Agent": "GitHub-Hookshot/abc123"},
    )

    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ Ping webhook successful!")
        return True
    else:
        print(f"   ❌ Ping failed: {response.text}")
        return False


def test_pr_webhook():
    """Test pull request webhook."""
    print("\n🔄 Testing pull request webhook...")

    test_repos = get_test_repositories()
    if not test_repos:
        return False

    # Use second repository if available, otherwise first
    repo = test_repos[1] if len(test_repos) > 1 else test_repos[0]

    payload = {
        "action": "opened",
        "number": 123,
        "repository": {
            "full_name": repo["full_name"],
            "name": repo["name"],
            "owner": {"login": repo["org"]},
        },
        "pull_request": {
            "number": 123,
            "title": "chore(deps): update dependency requests to v2.28.0",
            "body": "This PR updates the requests dependency.",
            "state": "open",
            "user": {"login": "renovate[bot]", "type": "Bot"},
            "head": {"ref": "renovate/requests-2.x", "sha": "abc123def456"},
            "base": {"ref": "main", "sha": "def456abc123"},
        },
    }

    response = requests.post(
        "http://localhost:8000/webhooks/github",
        json=payload,
        headers={
            "X-GitHub-Event": "pull_request",
            "User-Agent": "GitHub-Hookshot/abc123",
        },
    )

    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ PR webhook successful!")
        try:
            result = response.json()
            print(f"   📋 Response: {result}")
        except:
            print(f"   📋 Response: {response.text}")
        return True
    else:
        print(f"   ❌ PR webhook failed: {response.text}")
        return False


def test_check_suite_webhook():
    """Test check suite webhook."""
    print("\n✅ Testing check suite webhook...")

    test_repos = get_test_repositories()
    if not test_repos:
        return False

    # Use second repository if available, otherwise first
    repo = test_repos[1] if len(test_repos) > 1 else test_repos[0]

    payload = {
        "action": "completed",
        "repository": {
            "full_name": repo["full_name"],
            "name": repo["name"],
            "owner": {"login": repo["org"]},
        },
        "check_suite": {
            "id": 12345,
            "status": "completed",
            "conclusion": "success",
            "pull_requests": [{"number": 123, "head": {"sha": "abc123def456"}}],
        },
    }

    response = requests.post(
        "http://localhost:8000/webhooks/github",
        json=payload,
        headers={
            "X-GitHub-Event": "check_suite",
            "User-Agent": "GitHub-Hookshot/abc123",
        },
    )

    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ Check suite webhook successful!")
        try:
            result = response.json()
            print(f"   📋 Response: {result}")
        except:
            print(f"   📋 Response: {response.text}")
        return True
    else:
        print(f"   ❌ Check suite webhook failed: {response.text}")
        return False


def main():
    """Main test function."""
    print("🚀 Renovate PR Assistant - Webhook Testing")
    print("Testing against: http://localhost:8000")
    print("=" * 50)

    # Check if server is running
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server not responding to health check")
            return False
    except requests.exceptions.RequestException:
        print("❌ Cannot connect to server. Is it running on localhost:8000?")
        return False

    print("✅ Server is running")

    # Run tests
    tests = [test_ping_webhook, test_pr_webhook, test_check_suite_webhook]

    success_count = 0
    for test in tests:
        try:
            if test():
                success_count += 1
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")

    print(f"\n📊 Results: {success_count}/{len(tests)} tests passed")

    if success_count == len(tests):
        print("🎉 All webhook tests successful!")
        print("\n💡 Next steps:")
        print("   - Set up real GitHub webhooks pointing to your server")
        print("   - Configure Renovate in your target repositories")
        print("   - Watch the Renovate PR Assistant process real events!")
        return True
    else:
        print("⚠️  Some webhook tests failed. Check server logs for details.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
