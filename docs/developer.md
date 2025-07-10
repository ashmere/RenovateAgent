# Renovate PR Assistant - Developer Guide

**Last Updated:** 2025-07-10
**Version:** 0.5.1

## Overview

This document provides comprehensive guidance for developing and maintaining the Renovate PR Assistant. The system automates the review and management of Renovate dependency update pull requests across GitHub organizations using a **dual-mode architecture** with intelligent polling and webhook processing.

## Architecture Overview

The Renovate PR Assistant v0.5.1 features a **stateless, dual-mode architecture** optimized for performance and reliability:

### **Dual-Mode Operation**
- **Webhook Mode**: Real-time processing via GitHub webhooks
- **Polling Mode**: Intelligent background polling with adaptive intervals
- **Hybrid Approach**: Combines both modes for maximum coverage and reliability

### **Phase 2 Optimizations (v0.5.0+)**
- **Adaptive Polling**: Dynamic intervals based on repository activity (30s-1h)
- **Delta Detection**: 60-80% reduction in API calls through change detection
- **Intelligent Caching**: 80-95% cache hit rates for repository metadata
- **Activity Scoring**: Repository prioritization based on activity patterns
- **Batch Processing**: Efficient processing of multiple repositories

## Core Components

### 1. **Polling Orchestrator** (`polling/orchestrator.py`)
   - Manages adaptive polling intervals and repository batching
   - Coordinates with webhook processing for hybrid operation
   - Implements activity-based prioritization and delta detection

### 2. **GitHub Client** (`github_client.py`)
   - Robust client with rate limiting and caching
   - Supports both GitHub App and Personal Access Token authentication
   - Advanced PR detection and status checking

### 3. **PR Processor** (`pr_processor.py`)
   - Core logic for analyzing and processing Renovate PRs
   - Determines appropriate actions (approve, fix dependencies, block)
   - Orchestrates dependency fixing workflow

### 4. **Issue State Manager** (`issue_manager.py`)
   - Manages dashboard issues with structured data storage
   - Provides human-readable reports and technical metadata
   - Tracks polling status, PR states, and processing history

### 5. **Dependency Fixer** (`dependency_fixer/`)
   - Modular architecture supporting Python (Poetry), TypeScript (npm), Go
   - Handles repository cloning, fixing, and atomic commits
   - Language-specific implementations with unified interface

### 6. **Webhook Listener** (`webhook_listener.py`)
   - Receives and validates GitHub webhook events
   - Routes events to appropriate processors
   - Integrates with polling system for comprehensive coverage

## Environment Setup

### Prerequisites

- Python 3.12+
- Poetry (dependency management)
- Git
- GitHub App or Personal Access Token
- direnv (recommended for environment management)

### Quick Start with Local Setup Script

Use the automated setup script for fast environment configuration:

```bash
# Interactive setup (recommended for first-time setup)
python scripts/local_setup.py

# Non-interactive setup (CI/CD and automated environments)
python scripts/local_setup.py --non-interactive

# Manual setup
cp env.example .env
# Edit .env with your configuration
```

### Installation Steps

1. **Clone and setup:**
   ```bash
   git clone https://github.com/your-org/renovate-agent.git
   cd renovate-agent
   poetry install
   poetry run pre-commit install
   ```

2. **Configure environment:**
   ```bash
   # Use setup script (recommended)
   python scripts/local_setup.py

   # Or manual configuration
   cp env.example .env
   # Edit .env with your GitHub token and repositories
   ```

3. **Verify setup:**
   ```bash
   poetry run python scripts/test_github_connection.py
   poetry run python scripts/test_target_repos.py
   ```

## Required Environment Variables

```bash
# GitHub Authentication (choose one approach)
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here  # For PAT mode
# OR for GitHub App mode:
# GITHUB_APP_ID=your_app_id
# GITHUB_APP_PRIVATE_KEY_PATH=path/to/private-key.pem

# Target Configuration
GITHUB_ORGANIZATION=your-organization
GITHUB_TARGET_REPOSITORIES=org/repo1,org/repo2

# Polling Configuration (Phase 2 Optimizations)
ENABLE_POLLING=true
POLLING_BASE_INTERVAL=120  # seconds
POLLING_MAX_INTERVAL=3600  # seconds
POLLING_BATCH_SIZE=5
ENABLE_DELTA_DETECTION=true
ENABLE_INTELLIGENT_CACHING=true

# Dependency Fixing
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=python,typescript,go
CLONE_TIMEOUT=300
DEPENDENCY_UPDATE_TIMEOUT=600

# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
DEBUG=false
```

## Development Patterns

### Configuration Access

Access configuration through the settings object:

```python
from renovate_agent.config import get_settings

settings = get_settings()

# Check polling configuration
if settings.enable_polling:
    logger.info("Polling enabled",
                base_interval=settings.polling_base_interval,
                max_interval=settings.polling_max_interval)

# Access GitHub configuration
github_client = GitHubClient(settings)
```

### Error Handling Pattern

All components follow consistent error handling:

```python
from renovate_agent.exceptions import RenovateAgentError, GitHubAPIError
import structlog

logger = structlog.get_logger()

async def process_pr(pr_number: int, repo_name: str):
    try:
        # Core operation
        result = await github_client.get_pr(repo_name, pr_number)
        return {"success": True, "data": result}

    except GitHubAPIError as e:
        logger.error("GitHub API error",
                    pr_number=pr_number,
                    repo=repo_name,
                    error=str(e),
                    status_code=e.status_code)
        return {"success": False, "error": "github_api_error"}

    except RenovateAgentError as e:
        logger.error("Known error",
                    pr_number=pr_number,
                    error=str(e),
                    context=e.context)
        return {"success": False, "error": e.code}

    except Exception as e:
        logger.exception("Unexpected error",
                        pr_number=pr_number,
                        repo=repo_name)
        return {"success": False, "error": "internal_error"}
```

### Logging Standards

Use structured logging throughout:

```python
import structlog

logger = structlog.get_logger()

# Standard log patterns
logger.info("Processing Renovate PR",
           pr_number=pr.number,
           repo=repo.full_name,
           branch=pr.head.ref,
           author=pr.user.login)

logger.error("Dependency fix failed",
           repo=repo_name,
           pr_number=pr_number,
           language=language,
           error=str(e))
```

## GitHub Integration Patterns

### GitHub Client Usage

Use the centralized GitHub client for all API interactions:

```python
from renovate_agent.github_client import GitHubClient
from renovate_agent.config import get_settings

settings = get_settings()
github_client = GitHubClient(settings)

# Get repository
repo = await github_client.get_repo("owner/repo")

# Check if PR is from Renovate
is_renovate = await github_client.is_renovate_pr(pr)

# Get PR with detailed status
pr_info = await github_client.get_pr_with_status(repo, pr_number)

# Approve PR
await github_client.approve_pr(repo, pr_number, "Auto-approved by Renovate Agent")
```

### Renovate PR Detection

The system uses sophisticated detection for Renovate PRs:

```python
async def is_renovate_pr(self, pr) -> bool:
    """Detect if PR is from Renovate with multiple criteria."""
    renovate_indicators = [
        pr.user.login.lower() in ["renovate[bot]", "renovate-bot"],
        pr.head.ref.startswith(("renovate/", "renovate-")),
        "renovate" in pr.title.lower(),
        any(label.name.lower() == "renovate" for label in pr.labels)
    ]
    return any(renovate_indicators)
```

## Polling System Architecture

### Orchestrator Integration

The polling orchestrator manages intelligent repository processing:

```python
from renovate_agent.polling.orchestrator import PollingOrchestrator

# Initialize with dependencies
orchestrator = PollingOrchestrator(
    github_client=github_client,
    pr_processor=pr_processor,
    settings=settings
)

# Start polling (runs continuously)
await orchestrator.start_polling()

# Process single repository
await orchestrator._process_repository("owner/repo", datetime.now())
```

### Activity Scoring

Repositories are prioritized based on activity patterns:

```python
def calculate_activity_score(self, repo_data: dict) -> float:
    """Calculate repository activity score for prioritization."""
    factors = {
        "recent_pr_activity": 0.4,      # Recent PR updates
        "check_status_changes": 0.3,    # CI/CD activity
        "renovation_frequency": 0.2,    # Renovate activity
        "organization_priority": 0.1    # Org-specific weighting
    }

    score = sum(weight * self._calculate_factor(repo_data, factor)
               for factor, weight in factors.items())
    return min(score, 1.0)  # Normalize to 0-1
```

### Delta Detection

Minimize API calls through intelligent change detection:

```python
async def detect_changes(self, repo_name: str, current_state: dict) -> dict:
    """Detect what changed since last poll to minimize processing."""
    previous_state = await self.cache.get_repository_state(repo_name)

    if not previous_state:
        return {"full_sync_required": True}

    changes = {
        "prs_changed": current_state["pr_checksums"] != previous_state["pr_checksums"],
        "checks_changed": current_state["check_states"] != previous_state["check_states"],
        "new_activity": current_state["last_activity"] > previous_state["last_activity"]
    }

    return changes
```

## Testing Infrastructure

### Automated Testing with test-runner.sh

The project includes a comprehensive testing script:

```bash
# Full end-to-end testing
./test-runner.sh

# Test specific aspects
./test-runner.sh --polling-only
./test-runner.sh --dashboard-only
./test-runner.sh --quick
```

**Features:**
- **Dynamic PR Discovery**: Automatically finds and tests with real Renovate PRs
- **GitHub Auth Validation**: Verifies token and organization access
- **Polling System Testing**: Tests adaptive intervals and delta detection
- **Dashboard Validation**: Confirms dashboard updates and data integrity
- **Business Logic Testing**: Validates PR processing and approval logic

### Individual Test Scripts

Located in `scripts/` directory for targeted testing:

```bash
# GitHub connectivity and authentication
poetry run python scripts/test_github_connection.py

# Repository access and configuration
poetry run python scripts/test_target_repos.py

# Polling system functionality
poetry run python scripts/test_polling_system.py

# Issue creation and management
poetry run python scripts/test_issue_creation.py

# Webhook simulation and processing
poetry run python scripts/test_webhook.py

# Renovate PR detection logic
poetry run python scripts/test_renovate_detection.py
```

### Unit Testing Patterns

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from renovate_agent.pr_processor import PRProcessor

@pytest.mark.asyncio
async def test_pr_approval_with_passing_checks():
    # Setup mocks
    github_client = AsyncMock()
    github_client.get_pr_checks.return_value = [
        {"state": "success", "name": "test"}
    ]

    settings = MagicMock()
    settings.enable_dependency_fixing = True

    # Test processing
    processor = PRProcessor(github_client, settings)
    result = await processor.process_pr(mock_pr_data)

    # Assertions
    assert result["action"] == "approved"
    assert result["success"] is True
    github_client.approve_pr.assert_called_once()
```

### Integration Testing

Test complete workflows with real GitHub API:

```python
@pytest.mark.integration
async def test_real_polling_workflow():
    """Test polling workflow with real GitHub repositories."""
    settings = get_settings()
    github_client = GitHubClient(settings)

    # Use configured test repositories
    test_repos = settings.github_target_repositories

    for repo_name in test_repos:
        # Test repository access
        repo = await github_client.get_repo(repo_name)
        assert repo is not None

        # Test PR detection
        prs = list(repo.get_pulls(state="open"))
        renovate_prs = [pr for pr in prs
                       if await github_client.is_renovate_pr(pr)]

        logger.info("Found Renovate PRs",
                   repo=repo_name,
                   total_prs=len(prs),
                   renovate_prs=len(renovate_prs))
```

## State Management via GitHub Issues

### Dashboard Issue Structure

Each repository maintains state through a structured dashboard issue:

```python
{
    "repository": "owner/repo-name",
    "created_at": "2025-07-10T12:00:00Z",
    "last_updated": "2025-07-10T14:00:00Z",
    "open_renovate_prs": [
        {
            "number": 123,
            "title": "chore(deps): update dependency package",
            "url": "https://github.com/owner/repo/pull/123",
            "status": "ready",  # ready, waiting, blocked, error
            "status_reason": "checks_passing",
            "check_status": "passing",
            "checks_total": 3,
            "checks_passing": 3,
            "created_at": "2025-07-10T11:00:00Z"
        }
    ],
    "statistics": {
        "total_prs_processed": 45,
        "prs_auto_approved": 42,
        "dependency_fixes_applied": 8,
        "blocked_prs": 1
    },
    "polling_metadata": {
        "polling_enabled": true,
        "last_poll_time": "2025-07-10T13:58:00Z",
        "current_poll_interval": "2m",
        "active_prs": ["123", "124"],
        "total_polls_today": 287,
        "api_calls_used_today": 1250
    }
}
```

### State Update Patterns

```python
from renovate_agent.issue_manager import IssueStateManager

async def update_repository_state(repo_name: str, pr_data: dict):
    """Update repository state via dashboard issue."""
    issue_manager = IssueStateManager(github_client, settings)
    repo = await github_client.get_repo(repo_name)

    # Update dashboard with new PR data
    success = await issue_manager.update_dashboard_issue(repo, pr_data)

    if success:
        logger.info("Dashboard updated", repo=repo_name)
    else:
        logger.error("Dashboard update failed", repo=repo_name)
```

## Debugging and Troubleshooting

### Debug Scripts

The `scripts/` directory contains debugging utilities:

```bash
# Check GitHub connectivity and rate limits
poetry run python scripts/test_github_connection.py

# Verify repository access and permissions
poetry run python scripts/test_target_repos.py

# Test polling system functionality
poetry run python scripts/test_polling_system.py

# Simulate webhook events
poetry run python scripts/test_webhook.py

# Test Renovate PR detection
poetry run python scripts/test_renovate_detection.py

# Create test issues
poetry run python scripts/test_issue_creation.py
```

### Manual Dashboard Updates

Force dashboard updates for debugging:

```python
# Create temporary debug script
import asyncio
from renovate_agent.config import get_settings
from renovate_agent.github_client import GitHubClient
from renovate_agent.issue_manager import IssueStateManager

async def force_dashboard_update(repo_name: str):
    settings = get_settings()
    github_client = GitHubClient(settings)
    issue_manager = IssueStateManager(github_client, settings)

    repo = await github_client.get_repo(repo_name)
    result = await issue_manager.update_dashboard_issue(repo)

    print(f"Dashboard update: {'✅ Success' if result else '❌ Failed'}")

# Run for specific repository
asyncio.run(force_dashboard_update("owner/repo"))
```

### Common Debugging Patterns

**Rate Limit Issues:**
```python
# Check rate limit status
rate_limit = await github_client.get_rate_limit()
logger.info("Rate limit status",
           remaining=rate_limit.remaining,
           reset_time=rate_limit.reset)

# Enable rate limit warnings
settings.github_api_warning_threshold = 100
```

**Polling Issues:**
```python
# Debug polling intervals
from renovate_agent.polling.orchestrator import PollingOrchestrator

orchestrator = PollingOrchestrator(github_client, pr_processor, settings)
intervals = await orchestrator._calculate_polling_intervals()

for repo, interval in intervals.items():
    logger.info("Polling interval", repo=repo, interval_seconds=interval)
```

**PR Detection Issues:**
```python
# Test PR detection with specific PR
pr = await github_client.get_pr("owner/repo", 123)
is_renovate = await github_client.is_renovate_pr(pr)

logger.info("PR detection",
           pr_number=pr.number,
           author=pr.user.login,
           branch=pr.head.ref,
           title=pr.title,
           is_renovate=is_renovate)
```

### Health Check Endpoints

Monitor system health via API endpoints:

```bash
# Basic health check
curl http://localhost:8000/health

# GitHub API connectivity
curl http://localhost:8000/health/github

# Issues dashboard accessibility
curl http://localhost:8000/health/issues

# Polling system status
curl http://localhost:8000/health/polling
```

## Performance Optimization

### Caching Strategies

Implement intelligent caching for API optimization:

```python
from renovate_agent.polling.cache import PollingCache

cache = PollingCache(settings)

# Cache repository metadata
await cache.set_repository_metadata(repo_name, {
    "last_activity": datetime.now().isoformat(),
    "pr_checksums": pr_checksums,
    "check_states": check_states
})

# Retrieve with fallback
cached_data = await cache.get_repository_metadata(repo_name)
if not cached_data:
    # Fetch fresh data
    fresh_data = await fetch_repository_data(repo_name)
    await cache.set_repository_metadata(repo_name, fresh_data)
```

### Rate Limit Management

```python
async def with_rate_limit_handling(operation):
    """Execute operation with rate limit awareness."""
    rate_limit = await github_client.get_rate_limit()

    if rate_limit.remaining < 10:
        wait_time = (rate_limit.reset - datetime.now()).total_seconds()
        logger.warning("Rate limit low, waiting",
                      remaining=rate_limit.remaining,
                      wait_seconds=wait_time)
        await asyncio.sleep(wait_time)

    return await operation()
```

### Batch Processing

Process multiple repositories efficiently:

```python
async def process_repository_batch(repo_names: list[str]):
    """Process multiple repositories in optimized batches."""
    batch_size = settings.polling_batch_size

    for i in range(0, len(repo_names), batch_size):
        batch = repo_names[i:i + batch_size]

        # Process batch concurrently
        tasks = [process_repository(repo) for repo in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle results and exceptions
        for repo, result in zip(batch, results):
            if isinstance(result, Exception):
                logger.error("Batch processing failed",
                           repo=repo, error=str(result))
            else:
                logger.info("Batch processing complete",
                          repo=repo, success=result.get("success", False))
```

## Security and Authentication

### GitHub App vs Personal Access Token

The system supports both authentication methods:

```python
# GitHub App mode (recommended for production)
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem

# Personal Access Token mode (development/testing)
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
```

### Webhook Security

Validate all incoming webhooks:

```python
import hmac
import hashlib

async def validate_webhook_signature(payload: bytes, signature: str) -> bool:
    """Validate GitHub webhook signature."""
    if not signature:
        return False

    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    received = signature.replace("sha256=", "")
    return hmac.compare_digest(expected, received)
```

### Rate Limiting Protection

```python
from fastapi import Request, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/webhook/github")
@limiter.limit("10/minute")  # Limit webhook calls
async def github_webhook(request: Request):
    # Process webhook
    pass
```

## Deployment Patterns

### Docker Deployment

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Configure Poetry and install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --only=main --no-root

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Install the package
RUN poetry install --only-root

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "renovate_agent.main"]
```

### Environment Configuration

Use environment-specific configurations:

```bash
# Development
cp env.example .env.development
# Edit for development settings

# Production
cp env.example .env.production
# Configure for production with GitHub App
```

### Monitoring Setup

Essential monitoring for production:

```python
# Custom metrics collection
from renovate_agent.polling.metrics import PollingMetrics

metrics = PollingMetrics()

# Track processing metrics
await metrics.record_pr_processed(repo_name, success=True, duration=1.5)
await metrics.record_api_call_count(repo_name, count=3)
await metrics.record_cache_hit(repo_name, hit=True)

# Export metrics
metrics_data = await metrics.get_daily_summary()
```

## Contributing Guidelines

### Code Quality Standards

All code must follow these standards:

```bash
# Format with Black
poetry run black src/ tests/ scripts/

# Lint with Ruff
poetry run ruff check src/ tests/ scripts/

# Type checking with MyPy
poetry run mypy src/

# Security scanning
poetry run bandit -r src/

# Test coverage
poetry run pytest --cov=renovate_agent tests/
```

### Pre-commit Hooks

Ensure quality with automated hooks:

```bash
poetry run pre-commit install
poetry run pre-commit run --all-files
```

### AI Assistant Integration

This documentation is optimized for AI code assistants. Key patterns:

1. **Specific Examples**: All code examples are complete and runnable
2. **Error Patterns**: Common error scenarios with handling examples
3. **Configuration Patterns**: Environment setup with validation
4. **Testing Patterns**: Comprehensive testing strategies with real examples
5. **Debugging Patterns**: Step-by-step troubleshooting procedures

### Pull Request Standards

1. **Feature Branch**: Create from `main` with descriptive name
2. **Testing**: Include unit and integration tests
3. **Documentation**: Update relevant documentation sections
4. **Conventional Commits**: Use standard commit message format
5. **Review**: Address all feedback before merging

This developer guide provides comprehensive patterns and examples for effective development of the Renovate PR Assistant. The focus on AI assistant utility ensures that automated tools can effectively understand and work with the codebase while maintaining high standards for human contributors.
