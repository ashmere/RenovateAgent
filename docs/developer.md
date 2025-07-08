# Renovate PR Assistant - Developer Guide

**Last Updated:** 2025-07-08
**Version:** 0.1.0

## Overview

This document provides comprehensive guidance for developing and maintaining the Renovate PR Assistant. The system automates the review and management of Renovate dependency update pull requests across GitHub organizations.

## Architecture

The Renovate PR Assistant is built as a modular, stateless system with the following components:

### Core Components

1. **GitHub Webhook Listener** (`webhook_listener.py`)
   - Receives GitHub webhook events (pull_request, check_suite)
   - Validates webhook signatures
   - Routes events to appropriate processors

2. **PR Processing Engine** (`pr_processor.py`)
   - Core logic for analyzing and processing PRs
   - Determines appropriate actions (approve, fix dependencies)
   - Orchestrates dependency fixing workflow

3. **GitHub API Client** (`github_client.py`)
   - Robust client for GitHub REST API interactions
   - Handles authentication using GitHub App
   - Manages rate limiting and error handling

4. **Dependency Fixer** (`dependency_fixer/`)
   - Base architecture for language-specific dependency fixing
   - Supports Python (Poetry), TypeScript (npm/yarn), and Go
   - Handles repository cloning, fixing, and pushing changes

5. **GitHub Issue State Manager** (`issue_manager.py`)
   - Manages dashboard issues in repositories
   - Handles structured data storage and human-readable reports
   - Tracks open PRs and blocked status

## Environment Setup

### Prerequisites

- Python 3.8+
- Git
- GitHub App with appropriate permissions
- Virtual environment (recommended)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/renovate-agent.git
   cd renovate-agent
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

### Required Environment Variables

```bash
# GitHub App Configuration
GITHUB_APP_ID=your_github_app_id
GITHUB_APP_PRIVATE_KEY_PATH=path/to/your/private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret
GITHUB_ORGANIZATION=your-organization

# Database Configuration
DATABASE_URL=sqlite:///./renovate_agent.db

# Dependency Fixer Configuration
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=python,typescript,go
CLONE_TIMEOUT=300
DEPENDENCY_UPDATE_TIMEOUT=600
```

## GitHub App Setup

### Required Permissions

The GitHub App needs the following permissions:

- **Repository permissions:**
  - Contents: Write (to update lock files)
  - Issues: Write (to create/update dashboard issues)
  - Pull requests: Write (to approve PRs)
  - Checks: Read (to verify pre-merge status)
  - Metadata: Read (basic repository information)

- **Organization permissions:**
  - Members: Read (to identify organization members)

### Webhook Events

Subscribe to these webhook events:
- `pull_request` (opened, synchronize, closed)
- `check_suite` (completed)
- `issues` (opened, closed, labeled)

### Installation

Install the GitHub App on your organization or specific repositories where you want the Renovate PR Assistant to operate.

## Development Patterns

### Error Handling

All components follow a consistent error handling pattern:

```python
from renovate_agent.exceptions import RenovateAgentError

try:
    # operation
    result = await some_operation()
    return result
except RenovateAgentError as e:
    logger.error("Known error occurred", error=str(e), context=e.context)
    return {"error": {"code": e.code, "message": str(e)}}
except Exception as e:
    logger.exception("Unexpected error occurred")
    return {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}}
```

### Logging

Use structured logging throughout the application:

```python
import structlog

logger = structlog.get_logger()

logger.info("Processing PR",
            pr_number=pr.number,
            repository=pr.base.repo.full_name,
            author=pr.user.login)
```

### Configuration Access

Access configuration through the global settings object:

```python
from renovate_agent.config import settings

# Access configuration
if settings.enable_dependency_fixing:
    await fix_dependencies(pr)
```

## API Development

### Webhook Endpoint Pattern

All webhook endpoints follow this pattern:

```python
@router.post("/github")
async def handle_github_webhook(
    request: Request,
    github_event: str = Header(None, alias="X-GitHub-Event"),
    github_signature: str = Header(None, alias="X-Hub-Signature-256")
):
    # Validate signature
    await validate_webhook_signature(request, github_signature)

    # Parse payload
    payload = await request.json()

    # Process event
    await process_event(github_event, payload)

    return {"status": "processed"}
```

### GitHub API Integration

Use the GitHub client for all API interactions:

```python
from renovate_agent.github_client import GitHubClient

github_client = GitHubClient(settings.github_app_config)

# Get repository
repo = await github_client.get_repo("owner/repo")

# Approve PR
await github_client.approve_pr(repo, pr_number)
```

## Dependency Fixing Patterns

### Language-Specific Implementations

Each language fixer implements the `DependencyFixer` interface:

```python
class DependencyFixer:
    async def can_fix(self, repo_path: str) -> bool:
        """Check if this fixer can handle the repository."""
        pass

    async def fix_dependencies(self, repo_path: str, branch: str) -> bool:
        """Fix dependencies and return success status."""
        pass

    async def get_lock_files(self) -> List[str]:
        """Get list of lock files this fixer handles."""
        pass
```

### Repository Operations

All repository operations use temporary directories:

```python
import tempfile
from pathlib import Path

async def fix_repository_dependencies(repo_url: str, branch: str):
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "repo"

        # Clone repository
        await clone_repository(repo_url, repo_path, branch)

        # Fix dependencies
        success = await fix_dependencies(repo_path)

        if success:
            # Commit and push changes
            await commit_and_push(repo_path, branch)
```

## Testing Strategy

### Unit Tests

Test individual components in isolation:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_pr_approval():
    # Mock GitHub client
    github_client = AsyncMock()
    github_client.get_pr_checks.return_value = [{"state": "success"}]

    # Test PR processor
    pr_processor = PRProcessor(github_client, settings)
    result = await pr_processor.process_pr(pr_data)

    assert result["action"] == "approved"
    github_client.approve_pr.assert_called_once()
```

### Integration Tests

Test complete workflows:

```python
@pytest.mark.asyncio
async def test_dependency_fixing_workflow():
    # Create test repository
    test_repo = await create_test_repository()

    # Create failing PR
    pr = await create_renovate_pr(test_repo)

    # Process PR
    result = await process_pr_webhook(pr)

    # Verify fix was applied
    assert result["dependencies_fixed"] is True
    assert_lock_file_updated(test_repo)
```

### Testing with Real GitHub API

For integration testing, use real GitHub API with test repositories:

```python
# Use test organization for integration tests
TEST_GITHUB_ORG = "ai-code-assistant-test"

@pytest.mark.integration
async def test_real_github_integration():
    # This test uses real GitHub API
    # Requires TEST_GITHUB_APP_ID and TEST_GITHUB_APP_PRIVATE_KEY
    pass
```

## Database Schema

### Repository State

```sql
CREATE TABLE repositories (
    id INTEGER PRIMARY KEY,
    github_id INTEGER UNIQUE,
    full_name TEXT NOT NULL,
    last_processed TIMESTAMP,
    dashboard_issue_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### PR Processing History

```sql
CREATE TABLE pr_processing_history (
    id INTEGER PRIMARY KEY,
    repository_id INTEGER,
    pr_number INTEGER,
    action TEXT,
    success BOOLEAN,
    error_message TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repository_id) REFERENCES repositories(id)
);
```

## Monitoring and Observability

### Health Checks

The application provides health check endpoints:

- `/health` - Basic health check
- `/health/github` - GitHub API connectivity
- `/health/database` - Database connectivity

### Metrics

Track these key metrics:

- PRs processed per hour
- Success rate of dependency fixes
- GitHub API rate limit usage
- Processing time per PR

### Alerting

Set up alerts for:

- Failed dependency fixes
- GitHub API rate limit approaching
- Webhook processing errors
- Database connection failures

## Security Considerations

### Webhook Signature Validation

All incoming webhooks MUST be validated:

```python
import hmac
import hashlib

def validate_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected_signature}", signature)
```

### Private Key Management

- Store GitHub App private keys securely
- Use environment variables or secure key management
- Rotate keys regularly
- Never commit keys to version control

### Rate Limiting

Implement rate limiting for webhook endpoints:

```python
from fastapi import Request
from fastapi.responses import JSONResponse

async def rate_limit_middleware(request: Request, call_next):
    # Implement rate limiting logic
    if exceeded_rate_limit(request.client.host):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"}
        )

    response = await call_next(request)
    return response
```

## Deployment

### Production Requirements

- Python 3.8+
- PostgreSQL (recommended) or SQLite
- Redis for caching (optional)
- Reverse proxy (nginx recommended)
- SSL/TLS certificates

### Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY setup.py .
RUN pip install -e .

EXPOSE 8000

CMD ["uvicorn", "renovate_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment-Specific Configuration

Use different configuration files for different environments:

- `.env.development` - Development settings
- `.env.staging` - Staging environment
- `.env.production` - Production environment

## Troubleshooting

### Common Issues

1. **GitHub API Rate Limits**
   - Monitor rate limit headers
   - Implement exponential backoff
   - Use GraphQL for complex queries

2. **Webhook Signature Validation Failures**
   - Verify webhook secret matches
   - Check payload encoding
   - Validate signature algorithm

3. **Dependency Fixing Failures**
   - Check repository permissions
   - Verify language-specific tools are installed
   - Review timeout configurations

### Debug Mode

Enable debug mode for detailed logging:

```bash
DEBUG=true uvicorn renovate_agent.main:app --reload
```

### Log Analysis

Use structured logging for easier analysis:

```bash
# Filter logs by component
grep '"logger_name": "renovate_agent.pr_processor"' app.log

# Find error logs
grep '"level": "error"' app.log | jq .
```

## Contributing

### Code Style

- Use Black for code formatting
- Follow PEP 8 guidelines
- Use type hints throughout
- Write comprehensive docstrings

### Pre-commit Hooks

Set up pre-commit hooks:

```bash
pre-commit install
pre-commit run --all-files
```

### Pull Request Process

1. Create feature branch from main
2. Implement changes with tests
3. Update documentation
4. Submit PR with clear description
5. Address review feedback
6. Merge after approval

### Conventional Commits

Use conventional commit messages:

```
feat: add support for Gradle dependency fixing
fix: resolve webhook signature validation issue
docs: update API documentation
test: add integration tests for PR processing
```

This developer guide provides the foundation for effective development and maintenance of the Renovate PR Assistant. Follow these patterns and practices to ensure consistent, maintainable, and reliable code.
