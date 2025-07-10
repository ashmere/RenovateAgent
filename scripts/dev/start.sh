#!/bin/bash
# Start RenovateAgent development environment

set -e

echo "🚀 Starting RenovateAgent development environment..."

# Check if .env.local exists, otherwise use .env
if [ -f .env.local ]; then
    ENV_FILE=".env.local"
    echo "📄 Using .env.local"
else
    ENV_FILE=".env"
    echo "📄 Using .env"
fi

# Start services
docker-compose -f docker-compose.dev.yml --env-file $ENV_FILE up --build

echo "✅ Development environment started"
echo "📊 Health: http://localhost:8080/health"
echo "📊 Logs: docker-compose -f docker-compose.dev.yml logs -f"
echo "🔧 Shell: docker-compose -f docker-compose.dev.yml exec renovate-agent sh"
