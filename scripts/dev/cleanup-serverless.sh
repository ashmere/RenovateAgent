#!/bin/bash

# Cleanup script for serverless functions
# Stops all functions-framework processes and cleans up ports

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🧹 Cleaning up serverless functions...${NC}"

# Kill any functions-framework processes
echo "Stopping functions-framework processes..."
pkill -f "functions-framework" 2>/dev/null || echo "No functions-framework processes found"

# Kill any processes on port 8090 (default serverless port)
echo "Checking port 8090..."
PIDS=$(lsof -ti :8090 2>/dev/null || true)
if [ ! -z "$PIDS" ]; then
    echo "Killing processes on port 8090: $PIDS"
    kill -9 $PIDS 2>/dev/null || true
else
    echo "Port 8090 is free"
fi

# Kill any processes on port 8080 (fallback port)
echo "Checking port 8080..."
PIDS=$(lsof -ti :8080 2>/dev/null || true)
if [ ! -z "$PIDS" ]; then
    echo "Killing processes on port 8080: $PIDS"
    kill -9 $PIDS 2>/dev/null || true
else
    echo "Port 8080 is free"
fi

# Clean up any hanging Python processes related to renovate_agent
echo "Cleaning up renovate_agent Python processes..."
pkill -f "renovate_agent" 2>/dev/null || echo "No renovate_agent processes found"

# Remove any temporary log files
if [ -f "serverless.log" ]; then
    echo "Removing serverless.log"
    rm -f serverless.log
fi

echo -e "${GREEN}✅ Cleanup complete!${NC}"
echo "Ports 8080 and 8090 should now be available for testing."
