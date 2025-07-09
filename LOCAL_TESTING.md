# Local Testing Guide

This guide shows you how to run the Renovate PR Assistant locally for testing. The system now supports **dual-mode operation** with both **polling** (default for local testing) and **webhook** modes available.

## Prerequisites

Before starting, ensure you have:
- **Python 3.12+** installed
- **Poetry** for dependency management (`pip install poetry`)
- **direnv** for environment management (optional but recommended)
- **GitHub account** with access to target repositories

## Quick Start (3 minutes)

### Option 1: Automated Setup (Recommended - Polling Mode)

The setup script handles authentication, validation, and configuration with **polling as the default** for local testing:

```bash
# 1. Install dependencies
poetry install

# 2. Run the automated setup script
poetry run python scripts/local_setup.py
# This script will:
# - Detect GitHub CLI authentication or guide you through manual setup
# - Validate your GitHub access
# - Create a complete .env file with POLLING ENABLED by default
# - Configure repositories for polling monitoring
# - Set webhook mode as optional for testing

# 3. Test the connection
poetry run python scripts/test_github_connection.py

# 4. Test repository access
poetry run python scripts/test_target_repos.py

# 5. Test the polling system
poetry run python scripts/test_polling_system.py

# 6. Test webhook processing (optional - for webhook mode testing)
poetry run python scripts/test_webhook.py

# 7. Start the server (polling mode active by default)
poetry run python -m renovate_agent.main
```

### Option 2: Manual Token Setup

If you prefer manual setup or automated setup fails:

1. **Get a Personal Access Token:**
   - Go to: https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `repo`, `read:org`, `read:user`, `write:issues`
   - Copy the token

2. **Set up environment:**
   ```bash
   export GITHUB_TOKEN=your_token_here
   poetry install
   poetry run python scripts/local_setup.py
   ```

### Option 3: Docker Testing (Dual Mode)

For testing in a containerized environment similar to production:

```bash
# 1. Set up environment file (if not already done)
poetry install
poetry run python scripts/local_setup.py

# 2. Build and run with Docker (dual mode enabled)
docker build -t renovate-agent:test .
docker run --rm -p 8000:8000 --env-file .env renovate-agent:test

# 3. Or use Docker Compose (recommended)
docker-compose up --build

# 4. Test the containerized application
# In another terminal:
poetry run python scripts/test_polling_system.py  # Test polling
poetry run python scripts/test_webhook.py         # Test webhooks
```

**Docker Testing Benefits:**
- ✅ **Production parity**: Tests the exact same container used in production
- ✅ **Dual mode testing**: Both polling and webhook modes active
- ✅ **Isolation**: Clean environment independent of local Python setup
- ✅ **Multi-stage build**: Optimized image size and security
- ✅ **Easy cleanup**: `docker-compose down` removes everything

**Docker Testing Requirements:**
- Docker installed (or Colima on macOS)
- `.env` file configured (same as poetry method)
- Port 8000 available

### Option 4: Development with Docker Volume Mount

For development with live code reloading in Docker:

```bash
# Modify docker-compose.yml to add development volume mount
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Or manually with volume mount
docker run --rm -p 8000:8000 --env-file .env \
  -v $(pwd)/src:/app/src \
  renovate-agent:test
```

## Operation Modes

The system supports three operation modes for local testing:

### 1. Polling Mode (Default for Local Testing)
- **Best for**: Corporate firewalls, private networks, local development
- **Latency**: 2-5 minutes (configurable)
- **Requirements**: Outbound network connectivity only
- **Benefits**: No webhook setup required, works anywhere

### 2. Webhook Mode (Optional for Local Testing)
- **Best for**: Testing webhook security and real-time processing
- **Latency**: Real-time (immediate)
- **Requirements**: Webhook simulation via test scripts
- **Benefits**: Tests production webhook flow

### 3. Dual Mode (Both Active)
- **Best for**: Comprehensive testing and production simulation
- **Features**: Maximum reliability with redundant event sources
- **Benefits**: Tests both polling and webhook paths

## Testing Scripts Overview

The project includes several testing scripts to validate functionality:

| Script | Purpose | Expected Outcome | Operation Mode |
|--------|---------|------------------|----------------|
| `test_github_connection.py` | Validates GitHub API access | ✅ Should succeed with valid token | Both |
| `test_target_repos.py` | Tests repository access and PR analysis | ✅ Should find repositories and PRs | Both |
| `test_polling_system.py` | **NEW** Tests polling system components | ✅ Should poll repos and find PRs | Polling |
| `test_webhook.py` | Tests webhook security and processing | ✅ 401 for unsigned, 200 for signed webhooks | Webhook |

## Understanding Test Results

### Expected Behaviors (These are CORRECT):

#### Polling System Test (NEW)
```bash
🔄 Testing polling system...
   ✅ Polling configuration valid
   ✅ Rate limiter initialized
   ✅ State tracker ready
   ✅ Found 3 repositories for polling
   ✅ Discovered 2 Renovate PRs
   ✅ Polling orchestrator ready
   🚀 Polling system operational!
```

#### Webhook Security Test
```bash
🔒 Testing webhook security (unsigned requests)...
   Status: 401
   ✅ Security working! Unsigned webhooks properly rejected
```
**This is correct!** The system should reject unsigned webhooks in production.

#### Signed Webhook Test
```bash
🔐 Testing signed webhook (should be accepted)...
   Status: 200
   ✅ Signed webhook accepted! Authentication working correctly
```

#### Repository Access
```bash
✅ Repository accessible: your-repo
   Description: Your repository description
   Language: Python
   Private: True
   Has Issues: True
   Open PRs: 5
   Renovate PRs: 2 (polling will monitor these)
```

### Problematic Behaviors (These need fixing):

#### Authentication Issues
```bash
❌ Token validation failed: 401
❌ Organization/user 'org-name' not found or not accessible
```

#### Configuration Issues
```bash
❌ POLLING_REPOSITORIES environment variable not set
❌ Repository 'repo-name' must be in format 'org/repo'
```

#### Polling Issues
```bash
❌ Polling not enabled (check ENABLE_POLLING=true)
❌ No repositories configured for polling
❌ Rate limit exceeded - polling paused
```

## Environment Configuration

The setup script creates a comprehensive `.env` file with **polling enabled by default**:

```bash
# GitHub Authentication (Personal Access Token mode for development)
GITHUB_APP_ID=0
GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here
GITHUB_ORGANIZATION=your-org-or-username
GITHUB_WEBHOOK_SECRET=dev-secret

# Operation Mode Configuration (DEFAULT: Polling enabled for local testing)
ENABLE_POLLING=true                           # DEFAULT: Enabled for local testing
ENABLE_WEBHOOKS=false                         # DEFAULT: Disabled (optional for testing)
POLLING_INTERVAL_MINUTES=2                    # Poll every 2 minutes
POLLING_MAX_CONCURRENT_REPOS=5                # Process 5 repos concurrently

# Repository Configuration
GITHUB_TEST_REPOSITORIES=org/repo1,org/repo2
POLLING_REPOSITORIES=org/repo1,org/repo2     # Same as test repos by default

# Polling Rate Limiting
GITHUB_API_RATE_LIMIT=5000                   # API calls per hour
POLLING_RATE_LIMIT_BUFFER=1000               # Reserve 1000 calls
POLLING_RATE_LIMIT_THRESHOLD=0.8             # Throttle at 80% usage

# Dashboard Configuration
DASHBOARD_CREATION_MODE=renovate-only        # Options: test, any, none, renovate-only

# Dependency Fixing Configuration
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=python,typescript,go

# Server Configuration (for webhook mode testing)
HOST=127.0.0.1                              # Localhost only for security
PORT=8000
```

## Stateless Architecture

The Renovate PR Assistant uses a **stateless architecture** with **dual-mode operation**:

✅ **No database required** - uses GitHub Issues as state store
✅ **No persistent storage** - state maintained in GitHub Issues
✅ **Polling mode default** - works behind firewalls and private networks
✅ **Webhook mode optional** - for testing real-time webhook processing
✅ **Single container deployment** - no external dependencies
✅ **Environment-based configuration** - all settings via environment variables

This means:
- 🚀 **Faster setup** - no database to configure
- 🔒 **GitHub-native state** - dashboards are GitHub Issues
- 📊 **Visible state** - repository dashboards are accessible via GitHub UI
- 🧹 **No maintenance** - no database migrations or backups needed
- 🌐 **Network flexible** - polling works in any network environment

## Testing Details

### Polling System Testing (PRIMARY)

The polling test script validates the complete polling system:

```bash
poetry run python scripts/test_polling_system.py
# 🔄 Testing polling system configuration...
#    ✅ Polling enabled in configuration
#    ✅ Repository list configured
#    ✅ Rate limiter initialized successfully
#
# 🔍 Testing repository discovery...
#    ✅ Found 3 repositories for polling
#    ✅ All repositories accessible
#
# 🔄 Testing PR discovery...
#    ✅ Discovered 2 Renovate PRs across repositories
#    ✅ State tracking operational
#
# 🚀 Polling system ready for operation!
```

### Webhook Testing (OPTIONAL)

The webhook test script validates webhook security and processing:

#### 1. Security Validation (401 Expected)
Tests that unsigned webhooks are properly rejected:
```bash
poetry run python scripts/test_webhook.py
# 🔒 Testing webhook security (unsigned requests)...
#    Status: 401
#    ✅ Security working! Unsigned webhooks properly rejected
```

#### 2. Signed Webhook Processing (200 Expected)
Tests that properly signed webhooks are accepted:
```bash
# 🔐 Testing signed webhook (should be accepted)...
#    Status: 200
#    ✅ Signed webhook accepted! Authentication working correctly
```

#### 3. Renovate PR Processing (200 Expected)
Tests actual Renovate PR processing logic:
```bash
# 🔄 Testing Renovate PR webhook processing...
#    Status: 200
#    ✅ Renovate PR webhook processed successfully!
```

## Troubleshooting

### Configuration Issues

#### Wrong Operation Mode
```bash
❌ Issue: "No operation mode enabled"
✅ Solution: Ensure at least one of ENABLE_POLLING=true or ENABLE_WEBHOOKS=true
```

#### Missing Polling Repositories
```bash
❌ Issue: POLLING_REPOSITORIES not set
✅ Solution: Add to .env: POLLING_REPOSITORIES=org/repo1,org/repo2
```

#### Invalid SUPPORTED_LANGUAGES Format
```bash
❌ Wrong: SUPPORTED_LANGUAGES=["python", "typescript", "go"]
✅ Correct: SUPPORTED_LANGUAGES=python,typescript,go
```

### Authentication Issues

#### Token Scope Problems
```bash
❌ Issue: "Repository not found" for accessible repos
✅ Solution: Ensure token has 'repo', 'read:org', 'read:user', 'write:issues' scopes
```

#### Rate Limit Issues (Polling Mode)
```bash
❌ Issue: "Rate limit exceeded" during polling
✅ Solution: Increase POLLING_INTERVAL_MINUTES or reduce POLLING_MAX_CONCURRENT_REPOS
```

### Runtime Issues

#### Server Connection Failed (Webhook Mode)
```bash
❌ Issue: "Cannot connect to server. Is it running on localhost:8000?"
✅ Solution: Start server in another terminal: poetry run python -m renovate_agent.main
```

#### Polling Not Starting
```bash
❌ Issue: "Polling system not starting"
✅ Solution: Check ENABLE_POLLING=true and repository configuration
```

#### direnv Environment Loading Issues
```bash
❌ Issue: "direnv: error invalid line"
✅ Solution: Fix .env format (run local_setup.py again) or reload: direnv reload
```

### Import/Class Name Issues

#### IssueManager Import Error
```bash
❌ Issue: "cannot import name 'IssueManager'"
✅ Solution: Use 'IssueStateManager' instead - this is the correct class name
```

## Development Workflow

### Polling-based Development (Default)

Typical development session with polling mode:

```bash
# 1. Setup (once)
poetry run python scripts/local_setup.py

# 2. Validate configuration
poetry run python scripts/test_github_connection.py
poetry run python scripts/test_target_repos.py
poetry run python scripts/test_polling_system.py

# 3. Start server (polling mode active by default)
poetry run python -m renovate_agent.main
# Server will automatically start polling configured repositories every 2 minutes

# 4. Monitor polling in logs
# Watch for: "Polling cycle started" and "Found X Renovate PRs"
# Check GitHub Issues for dashboard updates

# 5. Code changes
# Make your changes...
poetry run python -m pytest tests/  # Run tests
poetry run pre-commit run --all-files  # Check code quality

# 6. Re-test
poetry run python scripts/test_polling_system.py  # Verify changes work
```

### Webhook-based Development (Optional)

For testing webhook functionality:

```bash
# 1. Enable webhooks in .env
# Set: ENABLE_WEBHOOKS=true

# 2. Start server
poetry run python -m renovate_agent.main

# 3. Test webhooks in another terminal
poetry run python scripts/test_webhook.py

# 4. Simulate specific PR events
poetry run python scripts/test_renovate_pr_simulation.py --org your-org --repo your-repo --pr 123
```

### Dual-mode Development

For comprehensive testing:

```bash
# 1. Enable both modes in .env
# Set: ENABLE_POLLING=true
# Set: ENABLE_WEBHOOKS=true

# 2. Start server (both modes active)
poetry run python -m renovate_agent.main

# 3. Test both systems
poetry run python scripts/test_polling_system.py  # Test polling
poetry run python scripts/test_webhook.py         # Test webhooks

# Server will log events from both sources:
# - "Polling cycle started" (every 2 minutes)
# - "Webhook received" (when test webhook sent)
```

### Docker-based Development

For development with Docker containers:

```bash
# 1. Setup (once)
poetry install  # Just for scripts
poetry run python scripts/local_setup.py

# 2. Validate configuration
poetry run python scripts/test_github_connection.py
poetry run python scripts/test_target_repos.py

# 3. Development cycle with Docker (dual mode by default)
docker-compose up --build  # Start server in container
poetry run python scripts/test_polling_system.py  # Test polling
poetry run python scripts/test_webhook.py         # Test webhooks

# 4. Code changes with live reload (if volume mounted)
# Make your changes... (container will restart automatically)
poetry run python -m pytest tests/  # Run tests on host
poetry run pre-commit run --all-files  # Check code quality

# 5. Re-test
poetry run python scripts/test_polling_system.py  # Verify changes work

# 6. Clean up
docker-compose down  # Stop and remove containers
```

## What You Get

Once running, you'll have:

**Polling Mode (Default)**:
- **Background polling** of configured repositories every 2 minutes
- **Automatic PR discovery** and processing
- **GitHub Issues dashboards** with polling status and timestamps
- **Rate limit aware** polling with intelligent throttling

**Webhook Mode (Optional)**:
- **Webhook endpoint:** `http://localhost:8000/webhooks/github`
- **Security validation** with HMAC signature checking
- **Real-time PR processing** when webhooks received

**Both Modes**:
- **Health check:** `http://localhost:8000/health`
- **API documentation:** `http://localhost:8000/docs`
- **GitHub Issues dashboards** with operation mode status
- **Real GitHub API integration** for testing

## Production Readiness Check

Before deploying to production, ensure:

✅ All test scripts pass
✅ Polling system working (default mode tested)
✅ Webhook signature validation working (401 for unsigned requests)
✅ Repository access confirmed for target organizations
✅ Environment variables properly configured for chosen mode(s)
✅ GitHub Issues created and updated correctly with polling metadata
✅ Dependency fixing working for supported languages
✅ Rate limiting respecting GitHub API quotas

## Differences from Production

| Aspect | Poetry (Local) | Docker (Local) | Production |
|--------|----------------|----------------|------------|
| **Default Mode** | 🔄 Polling | 🔄 Polling + Webhook | ⚡ Webhook (+ optional Polling) |
| **Authentication** | Personal Access Token | Personal Access Token | GitHub App |
| **Container** | Host Python | ✅ Ubuntu 24.04 + Python 3.13 | ✅ Ubuntu 24.04 + Python 3.13 |
| **Rate Limits** | 5,000/hour (PAT) | 5,000/hour (PAT) | 5,000/hour per installation |
| **Permissions** | All repos user can access | All repos user can access | Fine-grained per installation |
| **Security** | ✅ Enabled (same as prod) | ✅ Enabled (same as prod) | ✅ Enabled |
| **State Storage** | ✅ GitHub Issues (same) | ✅ GitHub Issues (same) | ✅ GitHub Issues |
| **Database** | ❌ None (stateless) | ❌ None (stateless) | ❌ None (stateless) |
| **Build Process** | Poetry install | ✅ Multi-stage Docker build | ✅ Multi-stage Docker build |
| **Environment** | Host dependencies | ✅ Isolated container | ✅ Isolated container |
| **Network Reqs** | 🌐 Outbound only (polling) | 🌐 Outbound only (polling) | ⚡ Inbound + Outbound (webhook) |

**Key Differences**:
- **Local testing defaults to POLLING** for firewall compatibility
- **Production typically uses WEBHOOKS** for real-time processing
- **Both can run in DUAL MODE** for maximum reliability

**Recommendation**: Use **Docker testing** for the highest production parity, especially before deployment.

## Next Steps

Once local testing works:

1. **Choose production mode**:
   - **Polling**: For private networks, corporate firewalls
   - **Webhook**: For public deployments, real-time processing
   - **Dual**: For maximum reliability

2. **Set up GitHub App** for production authentication (if using webhooks)

3. **Deploy to cloud provider** with appropriate network configuration:
   - **Polling**: Any environment with outbound connectivity
   - **Webhook**: Public endpoint with inbound connectivity

4. **Configure production settings**:
   - **Webhook**: Set up GitHub webhooks pointing to your deployed instance
   - **Polling**: Configure repository lists and intervals
   - **Dual**: Enable both modes with appropriate configuration

5. **Set up monitoring** and alerting for production use

6. **Configure repository allowlists** for target organizations

The stateless architecture with dual-mode operation makes deployment flexible - choose the mode that best fits your network environment!
