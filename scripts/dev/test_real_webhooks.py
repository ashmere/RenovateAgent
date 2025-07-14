#!/usr/bin/env python3
"""
Real webhook testing using ngrok tunnel.

This script provides automated testing capabilities for the serverless
RenovateAgent functions with real GitHub webhook delivery.
"""

import argparse
import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RealWebhookTester:
    """Test serverless function with real GitHub webhooks via ngrok."""

    def __init__(self, port: int = 8090, ngrok_url: Optional[str] = None):
        """Initialize the tester with optional ngrok URL."""
        self.port = port
        self.ngrok_url = ngrok_url
        self.function_process: Optional[subprocess.Popen] = None
        self.ngrok_process: Optional[subprocess.Popen] = None

    def start_function(self) -> None:
        """Start the local serverless function."""
        logger.info(f"Starting serverless function on port {self.port}")

        # Set environment for serverless mode
        env = os.environ.copy()
        env.update(
            {
                "DEPLOYMENT_MODE": "serverless",
                "DEBUG": "true",
            }
        )

        self.function_process = subprocess.Popen(
            [
                "functions-framework",
                "--target=renovate_webhook",
                "--source=src/renovate_agent/serverless/main.py",
                f"--port={self.port}",
                "--debug",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for function to start
        time.sleep(5)

        # Test health check
        try:
            response = requests.get(f"http://localhost:{self.port}/health", timeout=10)
            if response.status_code == 200:
                logger.info("✅ Function health check passed")
            else:
                raise Exception(f"Health check failed: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Function health check failed: {e}")
            raise

    def start_ngrok(self) -> str:
        """Start ngrok tunnel and return public URL."""
        if self.ngrok_url:
            logger.info(f"Using provided ngrok URL: {self.ngrok_url}")
            return self.ngrok_url

        logger.info("Starting ngrok tunnel")

        self.ngrok_process = subprocess.Popen(
            ["ngrok", "http", str(self.port), "--log", "stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for ngrok to start
        time.sleep(5)

        # Get ngrok URL with retries
        for attempt in range(5):
            try:
                response = requests.get("http://localhost:4040/api/tunnels", timeout=5)
                tunnels = response.json().get("tunnels", [])
                if tunnels:
                    self.ngrok_url = tunnels[0]["public_url"]
                    logger.info(f"✅ ngrok tunnel active: {self.ngrok_url}")
                    return self.ngrok_url
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/5 failed: {e}")
                time.sleep(2)

        raise Exception("Failed to get ngrok URL after 5 attempts")

    def test_health_check(self) -> Dict[str, Any]:
        """Test the health check endpoint."""
        if not self.ngrok_url:
            raise Exception("ngrok URL not available")

        logger.info("Testing health check endpoint")

        try:
            response = requests.get(f"{self.ngrok_url}/health", timeout=10)
            result = {
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "response": response.json() if response.content else None,
            }

            if result["success"]:
                logger.info("✅ Health check via ngrok successful")
            else:
                logger.warning(f"⚠️ Health check returned HTTP {response.status_code}")

            return result
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return {"error": str(e), "success": False}

    def test_webhook(
        self, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Test sending a webhook payload to the functions-framework endpoint."""
        if headers is None:
            headers = {}

        # Serialize payload to bytes (same as what requests would send)
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        # Auto-sign webhook if secret is available
        webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
        if webhook_secret and "X-Hub-Signature-256" not in headers:
            signature = (
                "sha256="
                + hmac.new(
                    webhook_secret.encode("utf-8"),
                    payload_bytes,
                    hashlib.sha256,
                ).hexdigest()
            )
            headers["X-Hub-Signature-256"] = signature
            logger.info("Auto-signing webhook request with GitHub signature")

        # Set content type
        headers["Content-Type"] = "application/json"

        try:
            response = requests.post(
                self.ngrok_url,
                data=payload_bytes,
                headers=headers,
                timeout=30,
            )

            result = {
                "status_code": response.status_code,
                "url": self.ngrok_url,
                "signed": "X-Hub-Signature-256" in headers,
            }

            if response.status_code == 200:
                try:
                    result["response"] = response.json()
                except Exception:
                    result["response"] = response.text
            else:
                result["error"] = response.text

            return result

        except Exception as e:
            logger.error(f"Failed to send webhook request: {e}")
            return {
                "status_code": 0,
                "error": str(e),
                "url": self.ngrok_url,
                "signed": "X-Hub-Signature-256" in headers,
            }

    def test_renovate_pr_webhook(
        self, repo: str, pr_number: int = 999
    ) -> Dict[str, Any]:
        """Test with a Renovate PR webhook payload."""
        payload = {
            "action": "opened",
            "pull_request": {
                "number": pr_number,
                "user": {"login": "renovate[bot]"},
                "head": {"ref": f"renovate/test-package-{pr_number}"},
                "title": f"Update test-package to latest (PR #{pr_number})",
                "state": "open",
                "body": "This is a test Renovate PR for webhook testing.",
            },
            "repository": {"full_name": repo},
        }

        logger.info(f"Testing Renovate PR webhook for {repo} PR #{pr_number}")
        return self.test_webhook(payload)

    def test_github_signature(
        self, payload: Dict[str, Any], secret: str
    ) -> Dict[str, Any]:
        """Test webhook with GitHub signature validation."""
        import hashlib
        import hmac

        payload_str = json.dumps(payload, separators=(",", ":"))
        signature = (
            "sha256="
            + hmac.new(
                secret.encode("utf-8"),
                payload_str.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        )

        headers = {"X-Hub-Signature-256": signature}
        logger.info("Testing webhook with GitHub signature")
        return self.test_webhook(payload, headers)

    def cleanup(self) -> None:
        """Stop all processes."""
        logger.info("Cleaning up processes")

        if self.function_process:
            self.function_process.terminate()
            try:
                self.function_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.function_process.kill()

        if self.ngrok_process:
            self.ngrok_process.terminate()
            try:
                self.ngrok_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.ngrok_process.kill()

    def run_test_suite(self) -> None:
        """Run comprehensive test suite."""
        logger.info("🧪 Running comprehensive webhook test suite")

        test_repo = os.getenv("GITHUB_ORGANIZATION", "test") + "/test-repo"

        try:
            # Test 1: Health check
            print("\n1️⃣ Testing health check endpoint...")
            health_result = self.test_health_check()
            print(f"   Result: {json.dumps(health_result, indent=2)}")

            # Test 2: Basic webhook
            print("\n2️⃣ Testing basic webhook...")
            basic_result = self.test_renovate_pr_webhook(test_repo, 999)
            print(f"   Result: {json.dumps(basic_result, indent=2)}")

            # Test 3: Different PR number
            print("\n3️⃣ Testing with different PR number...")
            pr_result = self.test_renovate_pr_webhook(test_repo, 1001)
            print(f"   Result: {json.dumps(pr_result, indent=2)}")

            # Test 4: GitHub signature (if secret available)
            webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
            if webhook_secret:
                print("\n4️⃣ Testing GitHub signature validation...")
                sig_payload = {
                    "action": "opened",
                    "pull_request": {
                        "number": 1002,
                        "user": {"login": "renovate[bot]"},
                    },
                    "repository": {"full_name": test_repo},
                }
                sig_result = self.test_github_signature(sig_payload, webhook_secret)
                print(f"   Result: {json.dumps(sig_result, indent=2)}")
            else:
                print("\n4️⃣ Skipping signature test (GITHUB_WEBHOOK_SECRET not set)")

            print("\n✅ Test suite completed!")

        except Exception as e:
            logger.error(f"❌ Test suite failed: {e}")
            raise


def main():
    """Main entry point for real webhook testing."""
    parser = argparse.ArgumentParser(
        description="Test RenovateAgent serverless webhooks"
    )
    parser.add_argument("--port", type=int, default=8090, help="Local function port")
    parser.add_argument("--url", type=str, help="ngrok URL (if already running)")
    parser.add_argument("--repo", type=str, help="Test repository (org/repo)")
    parser.add_argument("--pr", type=int, default=999, help="Test PR number")
    parser.add_argument("--suite", action="store_true", help="Run full test suite")
    parser.add_argument(
        "--start-services", action="store_true", help="Start function and ngrok"
    )

    args = parser.parse_args()

    # Default repository
    test_repo = args.repo or f"{os.getenv('GITHUB_ORGANIZATION', 'test')}/test-repo"

    tester = RealWebhookTester(port=args.port, ngrok_url=args.url)

    try:
        # Start services if requested
        if args.start_services or not args.url:
            print("🚀 Starting local services...")
            tester.start_function()
            ngrok_url = tester.start_ngrok()
            print(f"🌐 ngrok URL: {ngrok_url}")
            print(f"📋 Configure GitHub webhook to: {ngrok_url}")

        # Run test suite or single test
        if args.suite:
            tester.run_test_suite()
        else:
            print(f"🧪 Testing single webhook for {test_repo} PR #{args.pr}")
            result = tester.test_renovate_pr_webhook(test_repo, args.pr)
            print(f"📋 Result: {json.dumps(result, indent=2)}")

        # Services will be cleaned up in finally block
        if args.start_services or not args.url:
            print("\n✅ Testing completed successfully")

    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        if args.start_services or not args.url:
            tester.cleanup()


if __name__ == "__main__":
    main()
