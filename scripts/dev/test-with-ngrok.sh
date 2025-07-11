#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🌐 RenovateAgent ngrok Webhook Testing${NC}"
echo "================================================="

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo -e "${RED}❌ ngrok not found.${NC}"
    echo "Install from: https://ngrok.com/download"
    echo "Or via package manager:"
    echo "  macOS: brew install ngrok"
    echo "  Ubuntu: snap install ngrok"
    exit 1
fi

# Check required environment variables
if [ -z "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
    echo -e "${RED}❌ Error: GITHUB_PERSONAL_ACCESS_TOKEN is required${NC}"
    echo "Set this in your .env file or environment"
    exit 1
fi

if [ -z "$GITHUB_ORGANIZATION" ]; then
    echo -e "${RED}❌ Error: GITHUB_ORGANIZATION is required${NC}"
    echo "Set this in your .env file or environment"
    exit 1
fi

echo -e "${GREEN}✅ Environment variables configured${NC}"

# Parse command line arguments
PORT=${1:-8090}
REPO=${2:-$GITHUB_ORGANIZATION/test-repo}

echo -e "${YELLOW}📦 Starting local serverless function on port $PORT...${NC}"

# Cleanup any existing processes first
./scripts/dev/cleanup-serverless.sh >/dev/null 2>&1 || true

# Set serverless environment
export DEPLOYMENT_MODE=serverless
export DEBUG=true

# Start functions-framework in background
functions-framework \
    --target=renovate_webhook \
    --source=src/renovate_agent/serverless/main.py \
    --port=$PORT \
    --debug > serverless.log 2>&1 &

FUNCTION_PID=$!

# Wait for function to start and test health
sleep 5
echo -e "${YELLOW}🏥 Testing function health...${NC}"

HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/health || echo "000")
if [ "$HEALTH_CHECK" != "200" ]; then
    echo -e "${RED}❌ Function health check failed (HTTP $HEALTH_CHECK)${NC}"
    echo "Function logs:"
    tail -10 serverless.log 2>/dev/null || echo "No logs available"
    kill $FUNCTION_PID 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}✅ Function healthy and ready${NC}"

echo -e "${YELLOW}🌐 Starting ngrok tunnel...${NC}"

# Start ngrok tunnel
ngrok http $PORT --log stdout > ngrok.log 2>&1 &
NGROK_PID=$!
sleep 5

# Extract ngrok URL with retries
NGROK_URL=""
for i in {1..5}; do
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | jq -r '.tunnels[0].public_url' 2>/dev/null || echo "")
    if [ "$NGROK_URL" != "" ] && [ "$NGROK_URL" != "null" ]; then
        break
    fi
    echo -e "${YELLOW}⏳ Waiting for ngrok tunnel (attempt $i/5)...${NC}"
    sleep 2
done

if [ -z "$NGROK_URL" ] || [ "$NGROK_URL" = "null" ]; then
    echo -e "${RED}❌ Failed to get ngrok URL${NC}"
    echo "ngrok logs:"
    tail -10 ngrok.log 2>/dev/null || echo "No ngrok logs available"
    kill $FUNCTION_PID $NGROK_PID 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}✅ ngrok tunnel active: $NGROK_URL${NC}"

echo -e "${YELLOW}🧪 Testing webhook endpoint via ngrok...${NC}"

# Test the webhook endpoint through ngrok
TEST_RESULT=$(curl -X POST "$NGROK_URL" \
    -H "Content-Type: application/json" \
    -d '{
        "action": "opened",
        "pull_request": {
            "number": 999,
            "user": {"login": "renovate[bot]"},
            "head": {"ref": "renovate/test-package-1.0.0"},
            "title": "Test webhook via ngrok",
            "state": "open"
        },
        "repository": {"full_name": "test/repo"}
    }' \
    --silent \
    --max-time 30 \
    --write-out "HTTP_%{http_code}" || echo "FAILED")

if [[ "$TEST_RESULT" == *"HTTP_200"* ]]; then
    echo -e "${GREEN}✅ Webhook test successful!${NC}"
else
    echo -e "${YELLOW}⚠️ Webhook test returned: $TEST_RESULT${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Setup complete!${NC}"
echo -e "${YELLOW}📋 GitHub Webhook Configuration:${NC}"
echo "   Repository: https://github.com/$REPO"
echo "   Webhook URL: $NGROK_URL"
echo "   Content Type: application/json"
echo "   Events: Pull requests"
echo "   Secret: (leave empty for testing)"
echo ""
echo -e "${YELLOW}📝 To configure webhook in GitHub:${NC}"
echo "1. Go to: https://github.com/$REPO/settings/hooks"
echo "2. Click 'Add webhook'"
echo "3. Set Payload URL to: $NGROK_URL"
echo "4. Set Content type to: application/json"
echo "5. Select 'Pull requests' events"
echo "6. Click 'Add webhook'"
echo ""
echo -e "${BLUE}🔍 Monitoring:${NC}"
echo "Function logs: tail -f serverless.log"
echo "ngrok logs: tail -f ngrok.log"
echo "ngrok web interface: http://localhost:4040"
echo ""
echo -e "${BLUE}🧪 Test webhook manually:${NC}"
echo "python scripts/dev/test_real_webhooks.py --url $NGROK_URL"
echo ""
echo -e "${BLUE}🛑 Press Ctrl+C to stop all services${NC}"

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🧹 Cleaning up...${NC}"

    # Kill processes
    kill $FUNCTION_PID $NGROK_PID 2>/dev/null || true

    # Wait for processes to exit
    wait $FUNCTION_PID 2>/dev/null || true
    wait $NGROK_PID 2>/dev/null || true

    # Clean up log files
    rm -f serverless.log ngrok.log

    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

trap cleanup INT TERM

# Wait for interrupt or process exit
while kill -0 $FUNCTION_PID 2>/dev/null && kill -0 $NGROK_PID 2>/dev/null; do
    sleep 1
done

echo -e "${YELLOW}⚠️ One or more services stopped unexpectedly${NC}"
cleanup
