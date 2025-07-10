#!/bin/bash
# Run tests in development environment

echo "🧪 Running tests in development environment..."
docker-compose -f docker-compose.dev.yml exec renovate-agent     python -m pytest tests/ -v
