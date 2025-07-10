#!/bin/bash
# Start RenovateAgent development environment

set -e

echo "🚀 Starting RenovateAgent development environment..."

# Load environment variables
if [ -f .env.local ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
fi

# Start services
docker compose -f docker-compose.dev.yml up --build

echo "✅ Development environment started"
echo "📊 Logs: docker compose -f docker-compose.dev.yml logs -f"
echo "🔧 Shell: docker compose -f docker-compose.dev.yml exec     renovate-agent bash"
