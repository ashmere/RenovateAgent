#!/bin/bash

# Real-world test runner for PR #217 approval
set -e

echo "🚀 Starting real-world test against skyral-group/ee-sdlc PR #217"
echo "==============================================================="

# Check if credentials are configured
if ! grep -q "YOUR_" test-real.env; then
    echo "✅ Credentials appear to be configured"
else
    echo "❌ Please configure your GitHub credentials in test-real.env first"
    echo "   Required: GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_PATH, GITHUB_WEBHOOK_SECRET"
    exit 1
fi

# Build latest image
echo "🔨 Building Docker image..."
docker build -t renovate-agent:test .

# Stop any existing test containers
echo "🧹 Cleaning up existing containers..."
docker stop renovate-agent-real-test 2>/dev/null || true
docker rm renovate-agent-real-test 2>/dev/null || true

# Start container
echo "🚀 Starting container with polling..."
docker run --name renovate-agent-real-test \
    --env-file test-real.env \
    -p 8001:8000 \
    -d \
    renovate-agent:test

# Wait for startup
echo "⏳ Waiting for system startup..."
sleep 10

# Check health
echo "🩺 Checking system health..."
health_response=$(curl -s http://localhost:8001/health || echo "failed")
echo "Health check: $health_response"

# Monitor logs for 60 seconds
echo "📊 Monitoring polling activity for 60 seconds..."
echo "Looking for PR #217 detection and processing..."
echo "==============================================================="

timeout 60s docker logs -f renovate-agent-real-test || true

echo ""
echo "==============================================================="
echo "📊 Final system status:"
curl -s http://localhost:8001/health | python -m json.tool 2>/dev/null || echo "Health check failed"

echo ""
echo "🔍 Checking for approval activity in recent logs..."
docker logs renovate-agent-real-test 2>&1 | grep -i "approv\|process.*pr.*217\|renovate.*pr" | tail -10 || echo "No approval activity found yet"

echo ""
echo "📋 Test completed. Check the logs above for:"
echo "   ✅ PR #217 detected"
echo "   ✅ Renovate PR identified"
echo "   ✅ Approval attempted"
echo ""
echo "💡 To continue monitoring: docker logs -f renovate-agent-real-test"
echo "💡 To check PR status: Visit https://github.com/skyral-group/ee-sdlc/pull/217"
echo "💡 To stop test: docker stop renovate-agent-real-test && docker rm renovate-agent-real-test"
