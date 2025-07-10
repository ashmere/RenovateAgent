#!/bin/bash
# View RenovateAgent development logs

if [ "$1" = "-f" ]; then
    docker compose -f docker-compose.dev.yml logs -f
else
    docker compose -f docker-compose.dev.yml logs
fi
