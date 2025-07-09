#!/usr/bin/env python3
"""
Test script for the RenovateAgent polling system.

This script validates that the polling system components are properly
implemented and can be configured correctly.
"""

import asyncio
import os
import sys
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from renovate_agent.config import get_settings
from renovate_agent.github_client import GitHubClient
from renovate_agent.polling import (
    PollingOrchestrator,
    PollingStateTracker,
    RateLimitManager,
)
from renovate_agent.pr_processor import PRProcessor


async def test_polling_configuration():
    """Test that polling configuration is properly loaded."""
    print("🔧 Testing polling configuration...")

    settings = get_settings()
    polling_config = settings.polling_config

    print(f"   ✓ Polling enabled: {polling_config.enabled}")
    print(f"   ✓ Base interval: {polling_config.base_interval_seconds}s")
    print(f"   ✓ Max interval: {polling_config.max_interval_seconds}s")
    print(f"   ✓ Adaptive polling: {polling_config.adaptive_polling}")
    print(f"   ✓ Concurrent repos: {polling_config.concurrent_repo_polling}")

    return True


async def test_component_initialization():
    """Test that polling components can be initialized."""
    print("\n🏗️  Testing component initialization...")

    settings = get_settings()
    github_client = GitHubClient(settings.github_app_config)
    pr_processor = PRProcessor(github_client, settings)

    # Test PollingOrchestrator
    try:
        orchestrator = PollingOrchestrator(github_client, pr_processor, settings)
        print("   ✓ PollingOrchestrator initialized")
    except Exception as e:
        print(f"   ❌ PollingOrchestrator failed: {e}")
        return False

    # Test PollingStateTracker
    try:
        state_tracker = PollingStateTracker(github_client, settings)
        print("   ✓ PollingStateTracker initialized")
    except Exception as e:
        print(f"   ❌ PollingStateTracker failed: {e}")
        return False

    # Test RateLimitManager
    try:
        rate_limiter = RateLimitManager(github_client, settings)
        print("   ✓ RateLimitManager initialized")
    except Exception as e:
        print(f"   ❌ RateLimitManager failed: {e}")
        return False

    return True


async def test_orchestrator_methods():
    """Test basic orchestrator methods."""
    print("\n⚙️  Testing orchestrator methods...")

    settings = get_settings()
    github_client = GitHubClient(settings.github_app_config)
    pr_processor = PRProcessor(github_client, settings)
    orchestrator = PollingOrchestrator(github_client, pr_processor, settings)

    # Test is_running method
    try:
        is_running = orchestrator.is_running()
        print(f"   ✓ is_running() returned: {is_running}")
    except Exception as e:
        print(f"   ❌ is_running() failed: {e}")
        return False

    # Test rate limit checking (if GitHub token is available)
    if settings.github_personal_access_token or settings.github_app_id > 0:
        try:
            rate_status = await orchestrator.rate_limiter.check_rate_limits()
            print(f"   ✓ Rate limit check: {rate_status.remaining}/{rate_status.limit}")
        except Exception as e:
            print(f"   ⚠️  Rate limit check failed (expected without valid token): {e}")
    else:
        print("   ⚠️  Skipping rate limit test (no GitHub token configured)")

    return True


async def test_dashboard_integration():
    """Test dashboard integration with polling metadata."""
    print("\n📊 Testing dashboard integration...")

    settings = get_settings()
    github_client = GitHubClient(settings.github_app_config)
    state_tracker = PollingStateTracker(github_client, settings)

    # Test state tracker methods
    try:
        # Test getting last poll time (should return None for non-existent repo)
        last_poll = await state_tracker.get_last_poll_time("test/non-existent-repo")
        print(f"   ✓ get_last_poll_time() returned: {last_poll}")
    except Exception as e:
        print(f"   ❌ get_last_poll_time() failed: {e}")
        return False

    return True


async def main():
    """Main test function."""
    print("🚀 Starting RenovateAgent Polling System Tests")
    print("=" * 50)

    tests = [
        test_polling_configuration,
        test_component_initialization,
        test_orchestrator_methods,
        test_dashboard_integration,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")

    print("\n" + "=" * 50)
    print(f"📈 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Polling system is ready.")
        return 0
    else:
        print("❌ Some tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
