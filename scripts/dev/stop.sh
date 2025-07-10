#!/bin/bash
# Stop RenovateAgent development environment

echo "🛑 Stopping RenovateAgent development environment..."
docker-compose -f docker-compose.dev.yml down
echo "✅ Development environment stopped"
