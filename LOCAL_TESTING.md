# Local Testing Guide

This guide shows you how to run the Renovate PR Assistant locally for testing without setting up a full GitHub App.

## Prerequisites

Before starting, ensure you have:
- **Python 3.12+** installed
- **Poetry** for dependency management (`pip install poetry`)
- **direnv** for environment management (optional but recommended)
- **GitHub account** with access to target repositories

## Quick Start (3 minutes)

### Option 1: Automated Setup (Recommended)

The setup script handles authentication, validation, and configuration:

```bash
# 1. Install dependencies
poetry install

# 2. Run the automated setup script
poetry run python scripts/local_setup.py
# This script will:
# - Detect GitHub CLI authentication or guide you through manual setup
# - Validate your GitHub access
# - Create a complete .env file with proper formatting
# - Suggest test repositories based on your organization

# 3. Test the connection
poetry run python scripts/test_github_connection.py

# 4. Test repository access
poetry run python scripts/test_target_repos.py

# 5. Test webhook processing (includes security validation)
poetry run python scripts/test_webhook.py

# 6. Start the server
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

## Testing Scripts Overview

The project includes several testing scripts to validate functionality:

| Script | Purpose | Expected Outcome |
|--------|---------|------------------|
| `test_github_connection.py` | Validates GitHub API access | ✅ Should succeed with valid token |
| `test_target_repos.py` | Tests repository access and PR analysis | ✅ Should find repositories and PRs |
| `test_webhook.py` | Tests webhook security and processing | ✅ 401 for unsigned, 200 for signed webhooks |

## Understanding Test Results

### Expected Behaviors (These are CORRECT):

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
```

### Problematic Behaviors (These need fixing):

#### Authentication Issues
```bash
❌ Token validation failed: 401
❌ Organization/user 'org-name' not found or not accessible
```

#### Configuration Issues
```bash
❌ GITHUB_TEST_REPOSITORIES environment variable not set
❌ Repository 'repo-name' must be in format 'org/repo'
```

## Environment Configuration

The setup script creates a comprehensive `.env` file:

```bash
# GitHub Authentication (Personal Access Token mode for development)
GITHUB_APP_ID=0
GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here
GITHUB_ORGANIZATION=your-org-or-username
GITHUB_WEBHOOK_SECRET=dev-secret

# Test Repository Configuration
GITHUB_TEST_REPOSITORIES=org/repo1,org/repo2

# Dashboard Configuration
DASHBOARD_CREATION_MODE=renovate-only  # Options: test, any, none, renovate-only

# Dependency Fixing Configuration
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=python,typescript,go

# Security and Rate Limiting
GITHUB_API_RATE_LIMIT=5000
WEBHOOK_RATE_LIMIT=1000
```

## Stateless Architecture

The Renovate PR Assistant uses a **stateless architecture**:

✅ **No database required** - uses GitHub Issues as state store
✅ **No persistent storage** - state maintained in GitHub Issues
✅ **Single container deployment** - no external dependencies
✅ **Environment-based configuration** - all settings via environment variables

This means:
- 🚀 **Faster setup** - no database to configure
- 🔒 **GitHub-native state** - dashboards are GitHub Issues
- 📊 **Visible state** - repository dashboards are accessible via GitHub UI
- 🧹 **No maintenance** - no database migrations or backups needed

## Webhook Testing Details

The webhook test script validates three critical aspects:

### 1. Security Validation (401 Expected)
Tests that unsigned webhooks are properly rejected:
```bash
poetry run python scripts/test_webhook.py
# 🔒 Testing webhook security (unsigned requests)...
#    Status: 401
#    ✅ Security working! Unsigned webhooks properly rejected
```

### 2. Signed Webhook Processing (200 Expected)
Tests that properly signed webhooks are accepted:
```bash
# 🔐 Testing signed webhook (should be accepted)...
#    Status: 200
#    ✅ Signed webhook accepted! Authentication working correctly
```

### 3. Renovate PR Processing (200 Expected)
Tests actual Renovate PR processing logic:
```bash
# 🔄 Testing Renovate PR webhook processing...
#    Status: 200
#    ✅ Renovate PR webhook processed successfully!
```

## Troubleshooting

### Configuration Issues

#### Wrong Organization Format
```bash
❌ Issue: Testing against 'ashmere' but .env has 'skyral-group'
✅ Solution: Ensure GITHUB_ORGANIZATION matches your target org
```

#### Missing Test Repositories
```bash
❌ Issue: GITHUB_TEST_REPOSITORIES not set
✅ Solution: Add to .env: GITHUB_TEST_REPOSITORIES=org/repo1,org/repo2
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

#### Rate Limit Issues
```bash
❌ Issue: "Rate limit exceeded"
✅ Solution: Wait for reset or use GitHub App authentication for higher limits
```

### Runtime Issues

#### Server Connection Failed
```bash
❌ Issue: "Cannot connect to server. Is it running on localhost:8000?"
✅ Solution: Start server in another terminal: poetry run python -m renovate_agent.main
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

Typical development session:

```bash
# 1. Setup (once)
poetry run python scripts/local_setup.py

# 2. Validate configuration
poetry run python scripts/test_github_connection.py
poetry run python scripts/test_target_repos.py

# 3. Development cycle
poetry run python -m renovate_agent.main  # Start server
poetry run python scripts/test_webhook.py  # Test in another terminal

# 4. Code changes
# Make your changes...
poetry run python -m pytest tests/  # Run tests
poetry run pre-commit run --all-files  # Check code quality

# 5. Re-test
poetry run python scripts/test_webhook.py  # Verify changes work
```

## What You Get

Once running, you'll have:

- **Webhook endpoint:** `http://localhost:8000/webhooks/github`
- **Health check:** `http://localhost:8000/health`
- **API documentation:** `http://localhost:8000/docs`
- **GitHub Issues dashboards** created in test repositories
- **Real GitHub API integration** for testing

## Production Readiness Check

Before deploying to production, ensure:

✅ All test scripts pass
✅ Webhook signature validation working (401 for unsigned requests)
✅ Repository access confirmed for target organizations
✅ Environment variables properly configured
✅ GitHub Issues created and updated correctly
✅ Dependency fixing working for supported languages

## Differences from Production

| Aspect | Local Testing | Production |
|--------|---------------|------------|
| **Authentication** | Personal Access Token | GitHub App |
| **Rate Limits** | 5,000/hour (PAT) | 5,000/hour per installation |
| **Permissions** | All repos user can access | Fine-grained per installation |
| **Webhook Security** | ✅ Enabled (same as prod) | ✅ Enabled |
| **State Storage** | ✅ GitHub Issues (same) | ✅ GitHub Issues |
| **Database** | ❌ None (stateless) | ❌ None (stateless) |

## Next Steps

Once local testing works:

1. **Set up GitHub App** for production authentication
2. **Deploy to cloud provider** (supports stateless architecture)
3. **Configure production webhooks** pointing to your deployed instance
4. **Set up monitoring** and alerting for production use
5. **Configure repository allowlists** for target organizations

The stateless architecture makes deployment simple - just a single container with environment variables!
