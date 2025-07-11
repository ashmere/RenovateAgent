#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 RenovateAgent Serverless Local Testing${NC}"
echo "================================================="

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

# Check if functions-framework is installed
if ! command -v functions-framework &> /dev/null; then
    echo -e "${YELLOW}📦 Installing functions-framework...${NC}"
    poetry add functions-framework
fi

# Set serverless environment
export DEPLOYMENT_MODE=serverless
export DEBUG=true

# Parse command line arguments
COMMAND=${1:-"help"}
PORT=${2:-8080}

case $COMMAND in
    "start")
        echo -e "${BLUE}🔧 Starting functions-framework server on port $PORT...${NC}"

        # Start functions-framework
        functions-framework \
            --target=renovate_webhook \
            --source=src/renovate_agent/serverless/main.py \
            --port=$PORT \
            --debug &

        SERVER_PID=$!

        # Wait for server to start
        sleep 3

        echo -e "${GREEN}✅ Local serverless function ready at http://localhost:$PORT${NC}"
        echo -e "${YELLOW}🧪 Test endpoints:${NC}"
        echo "   POST http://localhost:$PORT/     - Webhook endpoint"
        echo "   GET  http://localhost:$PORT/health - Health check"
        echo ""
        echo -e "${YELLOW}🧪 Test with curl:${NC}"
        echo "curl -X POST http://localhost:$PORT/ -H 'Content-Type: application/json' -d '{\"action\":\"opened\",\"pull_request\":{\"number\":123}}'"
        echo ""
        echo -e "${YELLOW}🧪 Run test suite:${NC}"
        echo "python scripts/dev/test-serverless.py test"
        echo ""
        echo -e "${BLUE}🛑 Press Ctrl+C to stop${NC}"

        # Wait for interrupt
        trap "echo -e '\n${YELLOW}🛑 Stopping server...${NC}'; kill $SERVER_PID; wait $SERVER_PID; echo -e '${GREEN}✅ Server stopped${NC}'" INT
        wait $SERVER_PID
        ;;

    "test")
        echo -e "${BLUE}🧪 Running comprehensive test suite...${NC}"
        python scripts/dev/test-serverless.py test
        ;;

    "quick-test")
        echo -e "${BLUE}🧪 Running quick webhook test...${NC}"

        # Start server in background
        functions-framework \
            --target=renovate_webhook \
            --source=src/renovate_agent/serverless/main.py \
            --port=$PORT \
            --debug > /tmp/functions-framework.log 2>&1 &

        SERVER_PID=$!
        sleep 5

        # Test webhook
        echo -e "${YELLOW}Testing webhook endpoint...${NC}"
        curl -X POST http://localhost:$PORT/ \
            -H 'Content-Type: application/json' \
            -d '{
                "action": "opened",
                "pull_request": {
                    "number": 123,
                    "user": {"login": "renovate[bot]"},
                    "head": {"ref": "renovate/package-1.0.0"},
                    "title": "Update package to 1.0.0",
                    "state": "open"
                },
                "repository": {"full_name": "test/repo"}
            }' \
            --max-time 30 \
            --connect-timeout 10 \
            --silent \
            --show-error \
            | jq '.' || echo "Response received"

        # Test health check
        echo -e "${YELLOW}Testing health check endpoint...${NC}"
        curl -X GET http://localhost:$PORT/health \
            --max-time 10 \
            --connect-timeout 5 \
            --silent \
            --show-error \
            | jq '.' || echo "Health check response received"

        # Stop server
        kill $SERVER_PID
        wait $SERVER_PID 2>/dev/null || true
        echo -e "${GREEN}✅ Quick test completed${NC}"
        ;;

    "webhook")
        if [ -z "$2" ]; then
            echo -e "${RED}❌ Error: JSON payload required${NC}"
            echo "Usage: $0 webhook '{\"action\":\"opened\",\"pull_request\":{\"number\":123}}'"
            exit 1
        fi

        echo -e "${BLUE}🧪 Testing single webhook...${NC}"
        python scripts/dev/test-serverless.py webhook "$2"
        ;;

    "install-deps")
        echo -e "${BLUE}📦 Installing serverless dependencies...${NC}"
        poetry install

        # Check if functions-framework is available
        if poetry run functions-framework --help &> /dev/null; then
            echo -e "${GREEN}✅ functions-framework installed successfully${NC}"
        else
            echo -e "${YELLOW}📦 Installing functions-framework...${NC}"
            poetry add functions-framework
        fi

        # Check if requests is available (for testing)
        if poetry run python -c "import requests" &> /dev/null; then
            echo -e "${GREEN}✅ requests library available${NC}"
        else
            echo -e "${YELLOW}📦 Installing requests for testing...${NC}"
            poetry add --group dev requests
        fi

        echo -e "${GREEN}✅ Dependencies installed${NC}"
        ;;

    "help"|*)
        echo -e "${BLUE}RenovateAgent Serverless Local Testing${NC}"
        echo ""
        echo -e "${YELLOW}Commands:${NC}"
        echo "  start [port]    - Start local server (default port: 8080)"
        echo "  test            - Run comprehensive test suite"
        echo "  quick-test      - Run quick webhook and health check tests"
        echo "  webhook <json>  - Test single webhook with JSON payload"
        echo "  install-deps    - Install required dependencies"
        echo "  help            - Show this help message"
        echo ""
        echo -e "${YELLOW}Examples:${NC}"
        echo "  $0 start                                    # Start server on port 8080"
        echo "  $0 start 9000                               # Start server on port 9000"
        echo "  $0 test                                     # Run full test suite"
        echo "  $0 quick-test                               # Quick test"
        echo "  $0 webhook '{\"action\":\"opened\"}'         # Test specific webhook"
        echo ""
        echo -e "${YELLOW}Environment Variables Required:${NC}"
        echo "  GITHUB_PERSONAL_ACCESS_TOKEN - GitHub Personal Access Token"
        echo "  GITHUB_ORGANIZATION          - GitHub Organization name"
        echo ""
        echo -e "${YELLOW}Optional Environment Variables:${NC}"
        echo "  GITHUB_WEBHOOK_SECRET        - GitHub webhook secret (for signature validation)"
        echo "  GITHUB_TARGET_REPOSITORIES   - Comma-separated list of repositories"
        ;;
esac
