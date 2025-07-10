#!/bin/bash
# Open shell in RenovateAgent development container

docker-compose -f docker-compose.dev.yml exec renovate-agent bash
