# Local Testing Guide

This guide shows you how to run the Renovate PR Assistant locally for testing. The system now supports **dual-mode operation** with both **polling** (default for local testing) and **webhook** modes available, enhanced with **Phase 2 optimizations** including adaptive intervals, delta detection, intelligent caching, and comprehensive metrics.

## Prerequisites

Before starting, ensure you have:
- **Python 3.12+** installed
- **Poetry** for dependency management (`pip install poetry`)
- **Docker & Docker Compose** for containerized testing
- **direnv** for environment management (optional but recommended)
- **GitHub account** with access to target repositories

## Quick Start Options

### Option 1: Docker Compose Standalone Mode (Recommended)

The easiest way to test the complete system with all dependencies:

```bash
# 1. Clone and setup
git clone <repo-url>
cd RenovateAgent

# 2. Run interactive setup (creates .env.local)
python scripts/local_setup.py

# 3. Start the complete stack
docker-compose -f docker-compose.dev.yml up

# 4. Monitor logs
docker-compose -f docker-compose.dev.yml logs -f renovate-agent

# 5. Check health
curl http://localhost:8001/health
```

**What this provides**:
- ✅ **Complete isolation**: No local Python dependencies needed
- ✅ **Redis persistence**: Optional state persistence across restarts
- ✅ **Monitoring stack**: Prometheus + Grafana for metrics (optional)
- ✅ **Health checks**: Built-in container health monitoring
- ✅ **Development optimized**: Fast polling, detailed logging
- ✅ **Easy cleanup**: `docker-compose down` removes everything

### Option 2: Native Python Setup (Development)

For active development with immediate code changes:

```bash
# 1. Install dependencies
poetry install

# 2. Configure environment (Interactive setup)
python scripts/local_setup.py

# 3. Start the application in polling mode
poetry run python -m renovate_agent.main
```

### Option 3: Standalone Application Mode

For testing the new standalone architecture:

```bash
# 1. Setup environment (choose Docker mode)
python scripts/local_setup.py

# 2. Run standalone app directly
poetry run python -m renovate_agent.standalone

# 3. Or via Docker (recommended)
docker-compose -f docker-compose.dev.yml up renovate-agent
```

### Option 4: Serverless Mode (Local Functions Testing)

For testing the serverless functions locally using Google Cloud Functions Framework:

```bash
# 1. Install functions-framework (if not already installed)
poetry add functions-framework

# 2. Setup environment variables (using .envrc or manual export)
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token
export GITHUB_ORGANIZATION=your-org
export RENOVATE_BOT_USERNAMES="renovate[bot]"  # Optional: custom bot names

# 3. Start local serverless function (default port 8090)
./scripts/dev/test-serverless.sh start

# 4. Or run comprehensive test suite
./scripts/dev/test-serverless.sh test

# 5. Or use Python test script directly
python scripts/dev/test-serverless.py test
```

### Option 5: Real Webhook Testing with ngrok (NEW)

For end-to-end testing with real GitHub webhooks using ngrok tunneling:

```bash
# Prerequisites: Install ngrok
# macOS: brew install ngrok
# Ubuntu: snap install ngrok
# Or download from: https://ngrok.com/download

# 1. Setup environment variables
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token
export GITHUB_ORGANIZATION=your-org
export RENOVATE_BOT_USERNAMES="renovate[bot]"  # Optional

# 2. Start ngrok tunnel with local serverless function
./scripts/dev/test-with-ngrok.sh

# This will:
# - Start local functions-framework on port 8090
# - Create ngrok tunnel exposing the function publicly
# - Provide GitHub webhook configuration instructions
# - Test the webhook endpoint automatically

# 3. Configure GitHub webhook (follow script instructions):
# - Go to your test repository settings
# - Add webhook with the provided ngrok URL
# - Set content type to application/json
# - Select "Pull requests" events

# 4. Test with real GitHub webhooks or use the test script:
python scripts/dev/test_real_webhooks.py --suite

# 5. Monitor webhook delivery:
# - Function logs: tail -f serverless.log
# - ngrok web interface: http://localhost:4040
```

**What this provides**:
- ✅ **Local Cloud Function**: Tests the exact serverless deployment code
- ✅ **Functions Framework**: Uses Google's official local testing framework
- ✅ **Port 8090 Default**: Avoids conflicts with other services on 8080
- ✅ **Real Webhook Testing**: Processes actual GitHub webhook payloads
- ✅ **Custom Bot Support**: Tests configurable Renovate bot usernames
- ✅ **Health Endpoints**: Multiple health check endpoints (/health, /healthz, /)
- ✅ **Development Optimized**: Hot reloading, detailed logging, debug mode

## Docker Compose Standalone Mode (Detailed)

### Architecture Overview

The Docker Compose setup provides a complete testing environment:

```
┌─────────────────────┐    ┌─────────────────────┐
│   RenovateAgent     │    │      Redis          │
│   (Standalone)      │◄──►│   (Optional)        │
│                     │    │                     │
│ - Polling System    │    │ - State Persistence │
│ - Health Checks     │    │ - Cache Storage     │
│ - Metrics Export    │    │                     │
└─────────────────────┘    └─────────────────────┘
           │
           ▼
┌─────────────────────┐    ┌─────────────────────┐
│    Prometheus       │    │      Grafana        │
│   (Optional)        │    │   (Optional)        │
│                     │    │                     │
│ - Metrics Collection│    │ - Dashboards        │
│ - Alerting          │    │ - Visualization     │
└─────────────────────┘    └─────────────────────┘
```

### Configuration Files

**docker-compose.dev.yml** - Main composition:
- `renovate-agent`: Main application container
- `redis`: Optional persistence layer
- `prometheus`: Optional metrics collection
- `grafana`: Optional visualization

**Environment Configuration**:
```bash
# .env.local (created by setup script)
DEPLOYMENT_MODE=standalone
GITHUB_ORGANIZATION=your-org
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxxxx
ENABLE_POLLING=true
ENABLE_WEBHOOKS=false
POLLING_INTERVAL_SECONDS=60  # Fast for development
LOG_LEVEL=DEBUG
```

### Docker Compose Commands

**Basic Operations**:
```bash
# Start all services
docker-compose -f docker-compose.dev.yml up

# Start in background
docker-compose -f docker-compose.dev.yml up -d

# Start specific service
docker-compose -f docker-compose.dev.yml up renovate-agent

# View logs
docker-compose -f docker-compose.dev.yml logs -f

# Stop all services
docker-compose -f docker-compose.dev.yml down

# Clean up volumes
docker-compose -f docker-compose.dev.yml down -v
```

**Development Workflows**:
```bash
# Rebuild after code changes
docker-compose -f docker-compose.dev.yml build renovate-agent
docker-compose -f docker-compose.dev.yml up renovate-agent

# Shell into container
docker-compose -f docker-compose.dev.yml exec renovate-agent sh

# View container health
docker-compose -f docker-compose.dev.yml ps
```

**Profile-based Services**:
```bash
# Start with monitoring stack
docker-compose -f docker-compose.dev.yml --profile monitoring up

# Start with Redis persistence
docker-compose -f docker-compose.dev.yml --profile persistence up

# Start everything
docker-compose -f docker-compose.dev.yml --profile monitoring --profile persistence up
```

### Health Monitoring

**Container Health Checks**:
```bash
# Check container health
docker-compose -f docker-compose.dev.yml ps

# Expected output:
# renovate-agent    healthy
# redis            healthy (if enabled)
```

**Application Health Endpoint**:
```bash
# Basic health check
curl http://localhost:8001/health

# Expected response:
{
  "status": "healthy",
  "mode": "standalone",
  "deployment_mode": "standalone",
  "components": {
    "github_client": "healthy",
    "state_manager": {"status": "healthy", "stats": {...}},
    "polling_orchestrator": "healthy"
  }
}
```

**Detailed Monitoring**:
```bash
# Prometheus metrics (if monitoring profile enabled)
curl http://localhost:9090/metrics

# Grafana dashboard (if monitoring profile enabled)
open http://localhost:3000
# Login: admin/admin
```

### Troubleshooting Docker Setup

**Common Issues**:

1. **Port conflicts**:
   ```bash
   # Check port usage
   lsof -i :8001

   # Use different ports
   docker-compose -f docker-compose.dev.yml up --scale renovate-agent=0
   # Edit docker-compose.dev.yml ports section
   ```

2. **Environment not loaded**:
   ```bash
   # Verify .env.local exists
   ls -la .env.local

   # Check environment in container
   docker-compose -f docker-compose.dev.yml exec renovate-agent env | grep GITHUB
   ```

3. **GitHub connectivity**:
   ```bash
   # Test from container
   docker-compose -f docker-compose.dev.yml exec renovate-agent \
     curl -H "Authorization: token $GITHUB_PERSONAL_ACCESS_TOKEN" \
     https://api.github.com/user
   ```

4. **Build failures**:
   ```bash
   # Clean build
   docker-compose -f docker-compose.dev.yml build --no-cache renovate-agent

   # Check build logs
   docker-compose -f docker-compose.dev.yml build renovate-agent
   ```

### Performance Optimization

**Development Settings** (already configured in docker-compose.dev.yml):
```yaml
environment:
  - POLLING_INTERVAL_SECONDS=60        # Fast polling
  - POLLING_MAX_CONCURRENT_REPOS=3     # Moderate concurrency
  - LOG_LEVEL=DEBUG                    # Detailed logging
  - DEBUG=true                         # Debug mode
```

**Resource Limits**:
```yaml
deploy:
  resources:
    limits:
      memory: 512M        # Reasonable for development
      cpus: '0.5'         # Half CPU
    reservations:
      memory: 256M        # Minimum memory
```

**Volume Mounts** for development:
```yaml
volumes:
  - ./logs:/app/logs                   # Log persistence
  - /var/run/docker.sock:/var/run/docker.sock  # Docker access (if needed)
```

## Comprehensive Testing with Docker

### End-to-End Testing

**Automated Test Suite**:
```bash
# Run comprehensive tests with Docker
./test-runner.sh --docker

# The script will:
# 1. Start Docker Compose stack
# 2. Wait for services to be healthy
# 3. Run integration tests
# 4. Validate dashboard updates
# 5. Clean up containers
```

**Manual Testing Workflow**:
```bash
# 1. Start the stack
docker-compose -f docker-compose.dev.yml up -d

# 2. Wait for healthy status
while [[ "$(docker-compose -f docker-compose.dev.yml ps -q renovate-agent | xargs docker inspect -f '{{.State.Health.Status}}')" != "healthy" ]]; do
  echo "Waiting for container to be healthy..."
  sleep 5
done

# 3. Monitor initial polling cycle
docker-compose -f docker-compose.dev.yml logs -f renovate-agent | grep -E "(Polling cycle|Processing|Dashboard)"

# 4. Check metrics
curl http://localhost:8001/health | jq '.'

# 5. Verify GitHub connectivity
docker-compose -f docker-compose.dev.yml exec renovate-agent \
  python -c "
import asyncio
from renovate_agent.config import Settings
from renovate_agent.github_client import GitHubClient

async def test():
    settings = Settings()
    client = GitHubClient(settings)
    info = await client.get_rate_limit_info()
    print(f'Rate limit: {info}')

asyncio.run(test())
"
```

### Integration with CI/CD

**GitHub Actions Example**:
```yaml
name: Docker Integration Test
on: [push, pull_request]

jobs:
  docker-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Create test environment
        run: |
          cp env.example .env.local
          echo "GITHUB_PERSONAL_ACCESS_TOKEN=${{ secrets.GITHUB_TOKEN }}" >> .env.local
          echo "GITHUB_ORGANIZATION=test-org" >> .env.local

      - name: Start Docker stack
        run: docker-compose -f docker-compose.dev.yml up -d

      - name: Wait for health
        run: |
          timeout 60 bash -c 'until curl -f http://localhost:8001/health; do sleep 2; done'

      - name: Run integration tests
        run: |
          docker-compose -f docker-compose.dev.yml exec -T renovate-agent \
            python -m pytest tests/test_integration.py -v

      - name: Cleanup
        run: docker-compose -f docker-compose.dev.yml down -v
```

## Environment Configuration

### Recommended Local Testing Configuration (Phase 2 Optimized)

Create a `.env.local` file with these **optimized** settings for local testing:

```bash
# GitHub Authentication (choose one)
GITHUB_APP_ID=0
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
GITHUB_APP_PRIVATE_KEY_PATH=
GITHUB_WEBHOOK_SECRET=dev-secret
GITHUB_ORGANIZATION=your-org-name
GITHUB_API_URL=https://api.github.com

# Deployment Mode (NEW)
DEPLOYMENT_MODE=standalone

# Polling Mode (Phase 2 Optimized)
ENABLE_POLLING=true
POLLING_INTERVAL_SECONDS=120
POLLING_MAX_INTERVAL_SECONDS=600
POLLING_ADAPTIVE=true
POLLING_CONCURRENT_REPOS=5

# Repository Settings
GITHUB_REPOSITORY_ALLOWLIST=
GITHUB_TEST_REPOSITORIES=your-org/repo1,your-org/repo2
IGNORE_ARCHIVED_REPOSITORIES=true

# Dependency Fixing
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=python,typescript,go
CLONE_TIMEOUT=300
DEPENDENCY_UPDATE_TIMEOUT=600

# Dashboard
DASHBOARD_ISSUE_TITLE="Renovate PRs Assistant Dashboard"
UPDATE_DASHBOARD_ON_EVENTS=true
DASHBOARD_CREATION_MODE=renovate-only

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Logging
LOG_LEVEL=INFO
```

## Testing Modes

### 1. Polling Mode Testing (Default - Phase 2 Optimized)

**Features Tested**:
- ✅ Adaptive polling intervals based on repository activity
- ✅ Delta detection for efficient processing
- ✅ Intelligent caching with performance monitoring
- ✅ Real-time metrics and health scoring
- ✅ Rate limit management and adaptive throttling
- ✅ Graceful error handling and recovery

```bash
# Start in polling mode with optimizations
ENABLE_POLLING=true ENABLE_WEBHOOKS=false poetry run python -m renovate_agent.main

# Monitor real-time performance
curl http://localhost:8001/health
```

**Expected Behavior**:
- Starts with 2-minute polling interval
- Adapts to 1-minute for active repositories
- Scales to 5-15 minutes for inactive repositories
- Shows cache hit rates of 80-95% for metadata
- Processes only PRs with actionable changes
- Displays comprehensive metrics in GitHub Issues dashboard

### 2. Webhook Mode Testing (Traditional)

```bash
# Start in webhook mode
ENABLE_POLLING=false ENABLE_WEBHOOKS=true poetry run python -m renovate_agent.main

# Test with webhook simulation
poetry run python scripts/test_renovate_pr_simulation.py --org your-org --repo test-repo --pr 123
```

### 3. Dual Mode Testing (Maximum Reliability)

```bash
# Start both modes simultaneously
ENABLE_POLLING=true ENABLE_WEBHOOKS=true poetry run python -m renovate_agent.main
```

**Features**:
- Webhook events processed immediately
- Polling provides backup coverage
- Automatic deduplication prevents double-processing
- Cross-validation of both event sources

## Comprehensive Testing with test-runner.sh

The `test-runner.sh` script provides **comprehensive end-to-end testing** with intelligent PR discovery and dashboard validation:

### Features
- **✅ Dynamic PR Discovery**: Automatically finds open Renovate PRs across test repositories
- **✅ GitHub Authentication Validation**: Verifies connection and permissions
- **✅ Polling System Testing**: Tests real-world polling functionality with Docker
- **✅ Dashboard Validation**: Confirms dashboard updates and state persistence
- **✅ Business Logic Awareness**: Understands approval criteria and reasons for non-approval
- **✅ Comprehensive Reporting**: Detailed logs and test artifacts

### Usage

```bash
# Simple execution
./test-runner.sh

# The script will automatically:
# 1. Validate GitHub authentication and connectivity
# 2. Discover open Renovate PRs from configured repositories
# 3. Test polling system functionality using Docker
# 4. Monitor and validate dashboard updates
# 5. Generate comprehensive test reports with artifacts
```

### Test Scenarios

**Scenario 1: Active Renovate PRs Found**
- Attempts approval of suitable PRs
- Validates dashboard updates reflect changes
- Confirms polling system functionality

**Scenario 2: No Suitable PRs (Business Logic)**
- Tests dashboard update functionality instead
- Validates polling system detects PR state correctly
- Confirms proper business rule application

**Scenario 3: No Renovate PRs Found**
- Reports repository status
- Provides suggestions for test setup
- Validates basic connectivity

### Test Artifacts

All test runs generate artifacts in `test-artifacts/`:
- **`test-run-YYYYMMDD-HHMMSS.log`**: Complete test execution log
- **`test-results.json`**: Structured test results and metrics
- **`dashboard-before.json`**: Dashboard state before testing
- **`dashboard-after.json`**: Dashboard state after testing

## Phase 2 Features Testing

### Adaptive Polling Testing

Test the intelligent interval adjustment:

```bash
# 1. Create high-activity scenario (multiple PRs)
# 2. Monitor polling intervals in logs
# 3. Verify 1-2 minute intervals for active repos

# 4. Let repository go idle
# 5. Verify interval increases to 5-15 minutes
```

### Delta Detection Testing

Verify efficient change detection:

```bash
# 1. Create a PR and let it be processed
# 2. Make no changes - verify "unchanged" status
# 3. Add commits - verify "updated" status
# 4. Check logs for delta detection results
```

### Caching Performance Testing

Monitor cache effectiveness:

```bash
# Check cache statistics via health endpoint
curl http://localhost:8001/health | jq '.cache_stats'

# Expected: 80-95% hit rate for repository metadata
```

### Metrics Collection Testing

Access comprehensive metrics:

```bash
# View current cycle metrics
curl http://localhost:8001/metrics/current

# View repository performance summary
curl http://localhost:8001/metrics/repositories

# View global performance metrics
curl http://localhost:8001/metrics/global

# View health indicators
curl http://localhost:8001/metrics/health
```

## Advanced Testing Scenarios

### Rate Limiting Simulation

Test adaptive throttling:

```bash
# Set low rate limit for testing
GITHUB_API_RATE_LIMIT=100 poetry run python -m renovate_agent.main

# Monitor adaptive backoff in logs
# Verify graceful degradation
```

### Multi-Repository Testing

Test concurrent processing:

```bash
# Configure multiple repositories
POLLING_REPOSITORIES=org/repo1,org/repo2,org/repo3,org/repo4 poetry run python -m renovate_agent.main

# Monitor concurrent processing
# Verify activity-based prioritization
```

### Error Recovery Testing

Test resilience:

```bash
# 1. Start with invalid repository
# 2. Verify isolated error handling
# 3. Fix configuration
# 4. Verify automatic recovery
```

## Performance Expectations (Phase 2)

### Local Testing Performance
- **Memory Usage**: <30MB for 5-10 repositories
- **API Efficiency**: 60-80% reduction in API calls
- **Processing Speed**: 70-90% fewer unnecessary operations
- **Cache Hit Rates**: 80-95% for metadata, 60-80% for PR lists
- **Polling Intervals**: 1-15 minutes adaptive range

### Monitoring & Debugging

**Health Check Endpoint**:
```bash
curl http://localhost:8001/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "polling_enabled": true,
  "polling_running": true,
  "adaptive_intervals": true,
  "delta_detection": true,
  "caching_enabled": true,
  "cache_stats": {
    "hit_rate_percent": 87.5,
    "cache_size": 42
  },
  "health_score": 95,
  "health_status": "excellent"
}
```

**Real-time Logs**:
```bash
# Watch polling activity
poetry run python -m renovate_agent.main 2>&1 | grep -E "(Polling cycle|Delta detection|Cache)"

# Watch metrics
poetry run python -m renovate_agent.main 2>&1 | grep -E "(Metrics|Health|Performance)"
```

## Troubleshooting

### Common Issues

**1. High API Usage**:
```bash
# Check if caching is enabled
grep POLLING_ENABLE_CACHING .env

# Verify cache hit rates
curl http://localhost:8001/health | jq '.cache_stats.hit_rate_percent'
```

**2. Slow Processing**:
```bash
# Check if delta detection is enabled
grep POLLING_ENABLE_DELTA_DETECTION .env

# Monitor processing efficiency
curl http://localhost:8001/metrics/current | jq '.processing_efficiency'
```

**3. Rate Limiting**:
```bash
# Check rate limit status
curl http://localhost:8001/health | jq '.rate_limiting'

# Verify adaptive throttling
grep "Rate limit" logs.txt
```

### Debug Mode

Enable comprehensive debugging:

```bash
DEBUG=true LOG_LEVEL=DEBUG poetry run python -m renovate_agent.main
```

### Configuration Validation

```bash
# Validate environment configuration
poetry run python scripts/validate_config.py

# Test GitHub connectivity
poetry run python scripts/test_github_connection.py

# Validate repository access
poetry run python scripts/test_repository_access.py
```

## Integration Testing

### End-to-End Testing

Complete workflow validation:

```bash
# 1. Start the system
poetry run python -m renovate_agent.main &

# 2. Run comprehensive test suite
poetry run python scripts/test_polling_system.py

# 3. Verify dashboard updates
# Check GitHub Issues in test repositories

# 4. Validate metrics collection
curl http://localhost:8001/metrics/health
```

### Performance Benchmarking

```bash
# Run performance test suite
poetry run python scripts/benchmark_polling_performance.py

# Expected results:
# - API call reduction: 60-80%
# - Processing efficiency: 70-90%
# - Cache hit rate: 80-95%
# - Health score: >90
```

## Production Migration

### From Webhook to Polling

```bash
# 1. Enable dual mode first
ENABLE_POLLING=true ENABLE_WEBHOOKS=true

# 2. Monitor both modes
curl http://localhost:8001/health

# 3. Gradually disable webhooks
ENABLE_WEBHOOKS=false
```

### Performance Tuning

```bash
# Optimize for your environment
POLLING_INTERVAL_MINUTES=1                 # High-frequency
POLLING_MAX_CONCURRENT_REPOS=10           # High-throughput
POLLING_CACHE_TTL_SECONDS=600             # Extended caching
```

The **Phase 2 optimized polling system** provides enterprise-grade reliability and performance while maintaining the simplicity of local development testing.

## Serverless Mode Testing (Detailed)

### Architecture Overview

The serverless mode provides a Google Cloud Functions compatible environment for local testing:

```
┌─────────────────────────┐
│  Functions Framework    │
│  (Local Development)    │
│                         │
│ - Port 8090 (default)   │
│ - Hot Reloading         │
│ - Debug Mode            │
└─────────────────────────┘
           │
           ▼
┌─────────────────────────┐
│   Serverless Function   │
│   (renovate_webhook)    │
│                         │
│ - Webhook Processing    │
│ - Health Endpoints      │
│ - Error Handling        │
└─────────────────────────┘
           │
           ▼
┌─────────────────────────┐
│   RenovateAgent Core    │
│   (Business Logic)      │
│                         │
│ - PR Processing         │
│ - Bot Detection         │
│ - GitHub Integration    │
└─────────────────────────┘
```

### Environment Configuration

**Required Environment Variables**:
```bash
# GitHub Authentication
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
export GITHUB_ORGANIZATION=your-org-name

# Deployment Mode
export DEPLOYMENT_MODE=serverless
export DEBUG=true
```

**Optional Environment Variables**:
```bash
# Custom Renovate Bot Names (default: "renovate[bot]")
export RENOVATE_BOT_USERNAMES="renovate[bot]"
# Multiple organizations:
export RENOVATE_BOT_USERNAMES="renovate-org1[bot],renovate-org2[bot]"

# Webhook Security (disable for local testing)
export GITHUB_WEBHOOK_SECRET=""

# Target Repositories
export GITHUB_TARGET_REPOSITORIES="org/repo1,org/repo2"
```

### Testing Scripts Usage

#### test-serverless.sh - Main Testing Script

**Start Local Server**:
```bash
# Start on default port 8090
./scripts/dev/test-serverless.sh start

# Start on custom port
./scripts/dev/test-serverless.sh start 9000

# The server will show:
# ✅ Local serverless function ready at http://localhost:8090
# 🧪 Test endpoints:
#    POST http://localhost:8090/     - Webhook endpoint
#    GET  http://localhost:8090/health - Health check
```

**Run Test Suite**:
```bash
# Comprehensive test suite
./scripts/dev/test-serverless.sh test

# Quick webhook and health tests
./scripts/dev/test-serverless.sh quick-test

# Test specific webhook payload
./scripts/dev/test-serverless.sh webhook '{"action":"opened","pull_request":{"number":123}}'
```

#### test-serverless.py - Python Testing Framework

**Direct Usage**:
```bash
# Start server and wait
python scripts/dev/test-serverless.py start

# Run comprehensive test suite
python scripts/dev/test-serverless.py test

# Test single webhook
python scripts/dev/test-serverless.py webhook '{"action":"opened","pull_request":{"number":123}}'
```

**Automated Test Cases**:
- ✅ Health check endpoint validation
- ✅ Standard Renovate bot detection (`renovate[bot]`)
- ✅ Custom Renovate bot detection (`renovate-org[bot]`)
- ✅ Non-Renovate PR filtering
- ✅ Check suite completion events
- ✅ Error handling for invalid payloads

### Health Check Endpoints

The serverless function provides multiple health endpoints:

**Primary Health Check**:
```bash
curl http://localhost:8090/health

# Expected response:
{
  "status": "healthy",
  "deployment_mode": "serverless",
  "github_org": "your-org",
  "bot_usernames": ["renovate[bot]"],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Kubernetes-style Health Checks**:
```bash
# Liveness probe
curl http://localhost:8090/healthz

# Readiness probe (same endpoint)
curl http://localhost:8090/

# All return: {"status": "ok", "deployment_mode": "serverless"}
```

### Custom Bot Username Testing

Test the configurable bot username feature:

**Single Organization**:
```bash
export RENOVATE_BOT_USERNAMES="renovate-skyral[bot]"
./scripts/dev/test-serverless.sh start

# Test webhook with custom bot
curl -X POST http://localhost:8090/ \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "opened",
    "pull_request": {
      "number": 123,
      "user": {"login": "renovate-skyral[bot]"},
      "title": "Update dependency"
    },
    "repository": {"full_name": "test/repo"}
  }'
```

**Multiple Organizations**:
```bash
export RENOVATE_BOT_USERNAMES="renovate-org1[bot],renovate-org2[bot]"
./scripts/dev/test-serverless.sh test

# The test suite will validate both bot usernames
```

### Real-World Testing

Test with actual repositories and PRs:

**Live Repository Testing**:
```bash
# Set real organization and repositories
export GITHUB_ORGANIZATION=skyral-group
export GITHUB_TARGET_REPOSITORIES="skyral-group/ee-sdlc,skyral-group/skyral-ee-security-sandbox"
export RENOVATE_BOT_USERNAMES="renovate-skyral-group[bot]"

# Start serverless function
./scripts/dev/test-serverless.sh start

# Test with real PR webhook (from GitHub webhook settings)
# Or simulate using real PR data:
curl -X POST http://localhost:8090/ \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "opened",
    "pull_request": {
      "number": 218,
      "user": {"login": "renovate-skyral-group[bot]"},
      "title": "chore(deps): update dependency pip to v25 (main)",
      "head": {"ref": "renovate/pip-25.x"},
      "state": "open"
    },
    "repository": {"full_name": "skyral-group/ee-sdlc"}
  }'
```

### Troubleshooting Serverless Mode

**Common Issues**:

1. **Port Already in Use**:
   ```bash
   # Error: Address already in use, Port 8090 is in use
   # Solution: Use different port or kill existing process
   lsof -ti:8090 | xargs kill -9
   ./scripts/dev/test-serverless.sh start 8091
   ```

2. **Missing Environment Variables**:
   ```bash
   # Error: GITHUB_PERSONAL_ACCESS_TOKEN is required
   # Solution: Set in .envrc or export manually
   echo 'export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token' >> .envrc
   direnv allow
   ```

3. **Webhook Signature Validation Error**:
   ```bash
   # Error: No GitHub signature provided
   # Solution: Disable webhook secret for local testing
   export GITHUB_WEBHOOK_SECRET=""
   # Or unset it completely:
   unset GITHUB_WEBHOOK_SECRET
   ```

**Debug Mode**:
```bash
# Enable detailed logging
export DEBUG=true
export LOG_LEVEL=DEBUG

# Start with verbose output
./scripts/dev/test-serverless.sh start
```
