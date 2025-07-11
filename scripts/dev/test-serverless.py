#!/usr/bin/env python3
"""
Local testing of serverless functions using functions-framework.

This script provides automated testing capabilities for the serverless
RenovateAgent functions running locally via functions-framework.
"""

import json

# Configure simple logging
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class ServerlessLocalTester:
    """Local testing framework for serverless functions."""

    def __init__(self, base_url: str = "http://localhost:8090"):
        """Initialize the tester with the local server URL."""
        self.base_url = base_url
        self.process: Optional[subprocess.Popen] = None

    def start_local_server(self, port: int = 8090) -> None:
        """Start local functions-framework server."""
        logger.info(f"Starting local serverless function on port {port}")

        # Set environment for serverless mode
        env = os.environ.copy()
        env.update(
            {
                "DEPLOYMENT_MODE": "serverless",
                "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv(
                    "GITHUB_PERSONAL_ACCESS_TOKEN"
                ),
                "GITHUB_ORGANIZATION": os.getenv("GITHUB_ORGANIZATION"),
                "DEBUG": "true",
            }
        )

        # Start functions-framework
        self.process = subprocess.Popen(
            [
                "functions-framework",
                "--target=renovate_webhook",
                "--source=src/renovate_agent/serverless/main.py",
                f"--port={port}",
                "--debug",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to start
        time.sleep(5)
        logger.info(f"Local serverless function started at {self.base_url}")

    def test_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Test webhook processing locally."""
        try:
            logger.info(f"Testing webhook with action: {payload.get('action')}")

            response = requests.post(
                f"{self.base_url}/",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            result = {
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
                "execution_time": response.elapsed.total_seconds(),
            }

            logger.info(
                f"Webhook test completed: {result['status_code']} "
                f"in {result['execution_time']:.2f}s"
            )

            return result

        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"error": str(e)}

    def test_health_check(self) -> Dict[str, Any]:
        """Test health check endpoint."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            return {
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
            }
        except Exception as e:
            return {"error": str(e)}

    def stop_local_server(self) -> None:
        """Stop local functions-framework server."""
        if self.process:
            logger.info("Stopping local serverless function")
            self.process.terminate()
            self.process.wait()
            logger.info("Local serverless function stopped")

    def run_test_suite(self) -> None:
        """Run a comprehensive test suite."""
        logger.info("Starting serverless test suite")

        # Test payloads
        test_payloads = [
            {
                "name": "renovate_pr_opened",
                "payload": {
                    "action": "opened",
                    "pull_request": {
                        "number": 123,
                        "user": {"login": "renovate[bot]"},
                        "head": {"ref": "renovate/package-1.0.0"},
                        "title": "Update package to 1.0.0",
                        "state": "open",
                    },
                    "repository": {"full_name": "test/repo"},
                },
            },
            {
                "name": "non_renovate_pr",
                "payload": {
                    "action": "opened",
                    "pull_request": {
                        "number": 124,
                        "user": {"login": "developer"},
                        "head": {"ref": "feature/new-feature"},
                        "title": "Add new feature",
                        "state": "open",
                    },
                    "repository": {"full_name": "test/repo"},
                },
            },
            {
                "name": "check_suite_completed",
                "payload": {
                    "action": "completed",
                    "check_suite": {
                        "conclusion": "success",
                        "status": "completed",
                    },
                    "pull_request": {
                        "number": 123,
                        "user": {"login": "renovate[bot]"},
                        "head": {"ref": "renovate/package-1.0.0"},
                        "title": "Update package to 1.0.0",
                        "state": "open",
                    },
                    "repository": {"full_name": "test/repo"},
                },
            },
        ]

        results = []

        # Test health check
        logger.info("Testing health check endpoint")
        health_result = self.test_health_check()
        results.append({"test": "health_check", "result": health_result})

        # Test webhook payloads
        for test_case in test_payloads:
            logger.info(f"Testing webhook payload: {test_case['name']}")
            result = self.test_webhook(test_case["payload"])
            results.append({"test": test_case["name"], "result": result})

        # Print results summary
        logger.info("Test suite completed")
        print("\n" + "=" * 60)
        print("SERVERLESS TEST RESULTS")
        print("=" * 60)

        for result in results:
            test_name = result["test"]
            test_result = result["result"]
            status = "✅ PASS" if test_result.get("status_code") == 200 else "❌ FAIL"
            print(f"{test_name:20} {status}")
            if "error" in test_result:
                print(f"  Error: {test_result['error']}")

        print("=" * 60)


def main():
    """Main entry point for local testing."""
    if len(sys.argv) < 2:
        print("Usage: python test-serverless.py <command>")
        print("Commands:")
        print("  start    - Start local server and wait")
        print("  test     - Run test suite")
        print("  webhook  - Test single webhook (requires JSON payload)")
        return

    command = sys.argv[1]
    tester = ServerlessLocalTester()

    if command == "start":
        # Start server and wait for interrupt
        try:
            tester.start_local_server()
            print("Local serverless function ready at http://localhost:8090")
            print("Press Ctrl+C to stop")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            tester.stop_local_server()

    elif command == "test":
        # Run comprehensive test suite
        try:
            tester.start_local_server()
            time.sleep(2)  # Give server time to start
            tester.run_test_suite()
        finally:
            tester.stop_local_server()

    elif command == "webhook":
        # Test single webhook
        if len(sys.argv) < 3:
            print("Usage: python test-serverless.py webhook <json_payload>")
            return

        try:
            payload = json.loads(sys.argv[2])
            tester.start_local_server()
            time.sleep(2)
            result = tester.test_webhook(payload)
            print(json.dumps(result, indent=2))
        finally:
            tester.stop_local_server()

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
