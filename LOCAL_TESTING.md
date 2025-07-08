# Local Testing Guide

This guide shows you how to run the Renovate PR Assistant locally for testing without setting up a full GitHub App.

## Quick Start (2 minutes)

### Option 1: Using GitHub CLI (Recommended)

If you have `gh` CLI installed and authenticated:

```bash
# 1. Install dependencies
poetry install

# 2. Run the setup script
poetry run python scripts/local_setup.py

# 3. Test the connection
poetry run python scripts/test_github_connection.py

# 4. Test repository access (optional)
poetry run python scripts/test_target_repos.py

# 5. Start the server
poetry run python -m renovate_agent.main
```

### Option 2: Manual Token Setup

If you don't have GitHub CLI:

1. **Get a Personal Access Token:**
   - Go to: https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `repo`, `read:org`, `read:user`
   - Copy the token

2. **Set up environment:**
   ```bash
   export GITHUB_TOKEN=your_token_here
   poetry install
   poetry run python scripts/local_setup.py
   ```

3. **Test and run:**
   ```bash
   poetry run python scripts/test_github_connection.py
   poetry run python scripts/test_target_repos.py      # Test repository access
   poetry run python scripts/test_webhook.py           # Test webhook processing
   poetry run python -m renovate_agent.main
   ```

## What You Get

Once running, you'll have:

- **Webhook endpoint:** `http://localhost:8000/webhooks/github`
- **Health check:** `http://localhost:8000/health`
- **API docs:** `http://localhost:8000/docs`

## Testing GitHub Integration

The local setup allows you to:

✅ **Connect to real GitHub API** using your token
✅ **Test repository access** for your organizations
✅ **Test PR processing logic** with real PR data
✅ **Test dependency fixing** on real repositories
✅ **Debug webhook processing** with real GitHub events
✅ **Test dashboard creation** with different modes (test, any, none, renovate-only)

## Simulating GitHub Webhooks

To test webhook processing locally:

1. **Start the server:**
   ```bash
   poetry run python -m renovate_agent.main
   ```

2. **Send test webhook:** You can use curl or any HTTP client:
   ```bash
   curl -X POST http://localhost:8000/webhooks/github \
     -H "Content-Type: application/json" \
     -H "X-GitHub-Event: pull_request" \
     -d '{"action": "opened", "pull_request": {...}}'
   ```

3. **Use GitHub CLI to trigger real events:**
   ```bash
   # Create a test PR (will trigger real webhook if configured)
   gh pr create --title "Test PR" --body "Testing Renovate PR Assistant"
   ```

## Real Repository Testing

With your PAT, you can test against real repositories:

```bash
# Test on specific repositories
export GITHUB_TEST_REPOSITORIES="yourusername/repo1,yourusername/repo2"

# The Renovate PR Assistant will:
# - Read real PR data
# - Check actual CI status
# - Access real dependency files
# - Make real GitHub API calls
# - Filter repositories based on allowlist (if configured)
```

## Environment Variables

The local setup creates these environment variables:

```bash
# Development mode (uses PAT instead of GitHub App)
GITHUB_APP_ID=0
GITHUB_PERSONAL_ACCESS_TOKEN=your_token_here
GITHUB_ORGANIZATION=yourusername

# Optional: Repository filtering
GITHUB_REPOSITORY_ALLOWLIST=repo1,repo2  # If empty, monitors all repos
GITHUB_TEST_REPOSITORIES=org/repo1,org/repo2  # For testing

# Local server
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Dashboard configuration
DASHBOARD_CREATION_MODE=test  # For testing: create dashboards for any PR

# Dependency fixing
ENABLE_DEPENDENCY_FIXING=true
SUPPORTED_LANGUAGES=python,typescript,go
```

## Troubleshooting

### "Authentication failed"
- Check your token has the right scopes: `repo`, `read:org`, `read:user`
- Verify the token isn't expired
- Make sure `GITHUB_PERSONAL_ACCESS_TOKEN` is set

### "Organization not found"
- Use your GitHub username instead of organization name
- Check you have access to the organization

### "Rate limit exceeded"
- Personal tokens have lower rate limits than GitHub Apps
- Wait a few minutes and try again
- Use `python scripts/test_github_connection.py` to check limits

### "Repository not processed"
- Check if repository is archived (archived repos are ignored by default)
- Verify repository is in allowlist (if `GITHUB_REPOSITORY_ALLOWLIST` is set)
- Ensure you have proper permissions to access the repository

## Next Steps

Once local testing works:

1. **Deploy to production** with proper GitHub App setup
2. **Configure real webhooks** pointing to your deployed instance
3. **Set up monitoring** and logging for production use

## Differences from Production

Local testing mode:
- ✅ Uses Personal Access Token (simpler setup)
- ✅ Full GitHub API access for testing
- ❌ No webhook signature validation
- ❌ Limited rate limits vs GitHub App
- ❌ No fine-grained permissions
