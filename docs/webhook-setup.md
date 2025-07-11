# GitHub Webhook Setup for RenovateAgent Serverless Testing

This document provides instructions for setting up GitHub webhooks to test the RenovateAgent serverless functionality.

## Prerequisites

- GitHub CLI (`gh`) installed and authenticated
- Admin access to the target repository
- RenovateAgent serverless function deployed or running locally

## GitHub CLI Installation

If you don't have GitHub CLI installed:

```bash
# macOS
brew install gh

# Linux
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh

# Windows
winget install --id GitHub.cli
```

Authenticate with GitHub:
```bash
gh auth login
```

## Repository-Level Webhook Setup

For initial testing, we'll create repository-level webhooks on the specified repositories:
- `skyral-group/ee-sdlc`
- `skyral-group/skyral-ee-security-sandbox`

### Step 1: Generate Webhook Secret

```bash
# Generate a random webhook secret
WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "Generated webhook secret: $WEBHOOK_SECRET"

# Save this secret - you'll need it for your serverless function
echo "GITHUB_WEBHOOK_SECRET=$WEBHOOK_SECRET" >> .env
```

### Step 2: Create Repository Webhook

#### For Local Testing (functions-framework)

```bash
# Set variables
REPO_NAME="skyral-group/ee-sdlc"  # or skyral-group/skyral-ee-security-sandbox
WEBHOOK_URL="https://your-ngrok-url.ngrok.io"  # See ngrok setup below
WEBHOOK_SECRET="your-generated-secret"

# Create the webhook
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/$REPO_NAME/hooks \
  -f name='web' \
  -f active=true \
  -F 'events[]=pull_request' \
  -F 'events[]=check_suite' \
  -F 'events[]=push' \
  -f config[url]="$WEBHOOK_URL" \
  -f config[content_type]='application/json' \
  -f config[secret]="$WEBHOOK_SECRET" \
  -f config[insecure_ssl]='0'
```

#### For Cloud Function Testing

```bash
# Set variables
REPO_NAME="skyral-group/ee-sdlc"  # or skyral-group/skyral-ee-security-sandbox
WEBHOOK_URL="https://your-region-your-project.cloudfunctions.net/renovate-webhook"
WEBHOOK_SECRET="your-generated-secret"

# Create the webhook
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/$REPO_NAME/hooks \
  -f name='web' \
  -f active=true \
  -F 'events[]=pull_request' \
  -F 'events[]=check_suite' \
  -F 'events[]=push' \
  -f config[url]="$WEBHOOK_URL" \
  -f config[content_type]='application/json' \
  -f config[secret]="$WEBHOOK_SECRET" \
  -f config[insecure_ssl]='0'
```

### Step 3: Verify Webhook Creation

```bash
# List webhooks for the repository
gh api \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/$REPO_NAME/hooks

# Get specific webhook details
HOOK_ID=123456  # Replace with actual hook ID from above
gh api \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/$REPO_NAME/hooks/$HOOK_ID
```

## Local Testing Setup with ngrok

For testing with local functions-framework, you'll need to expose your local server to the internet:

### Step 1: Install ngrok

```bash
# macOS
brew install ngrok

# Linux
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# Windows
winget install ngrok.ngrok
```

### Step 2: Start Local Server and ngrok

```bash
# Terminal 1: Start local functions-framework server
./scripts/dev/test-serverless.sh start 8080

# Terminal 2: Start ngrok tunnel
ngrok http 8080

# Copy the https URL from ngrok (e.g., https://abc123.ngrok.io)
# Use this URL when creating the webhook
```

### Step 3: Test Webhook

```bash
# Create a test PR or push to trigger the webhook
# Check the ngrok web interface at http://localhost:4040 to see webhook deliveries
# Check your local server logs for processing
```

## Webhook Events

The RenovateAgent serverless function listens for these GitHub events:

### Pull Request Events
- `opened` - When a PR is opened
- `synchronize` - When a PR is updated with new commits
- `reopened` - When a PR is reopened
- `closed` - When a PR is closed
- `ready_for_review` - When a draft PR is marked ready for review

### Check Suite Events
- `completed` - When CI/CD checks complete
- `requested` - When checks are requested

### Push Events
- `push` - When code is pushed (for dashboard updates)

## Webhook Payload Examples

### Pull Request Opened
```json
{
  "action": "opened",
  "pull_request": {
    "number": 123,
    "title": "Update dependency package to 1.0.0",
    "user": {
      "login": "renovate[bot]"
    },
    "head": {
      "ref": "renovate/package-1.0.0"
    },
    "state": "open"
  },
  "repository": {
    "full_name": "skyral-group/ee-sdlc"
  }
}
```

### Check Suite Completed
```json
{
  "action": "completed",
  "check_suite": {
    "conclusion": "success",
    "status": "completed"
  },
  "pull_request": {
    "number": 123,
    "user": {
      "login": "renovate[bot]"
    }
  },
  "repository": {
    "full_name": "skyral-group/ee-sdlc"
  }
}
```

## Troubleshooting

### Webhook Not Firing

1. **Check webhook configuration**:
   ```bash
   gh api /repos/$REPO_NAME/hooks/$HOOK_ID
   ```

2. **Verify webhook URL is accessible**:
   ```bash
   curl -X POST your-webhook-url -H "Content-Type: application/json" -d '{"test": true}'
   ```

3. **Check webhook deliveries**:
   ```bash
   gh api /repos/$REPO_NAME/hooks/$HOOK_ID/deliveries
   ```

### Webhook Signature Validation Failing

1. **Verify webhook secret matches**:
   ```bash
   echo $GITHUB_WEBHOOK_SECRET
   ```

2. **Check environment variable in function**:
   ```bash
   # For local testing
   export GITHUB_WEBHOOK_SECRET="your-secret"

   # For Cloud Function, set in environment variables
   ```

### Local Testing Issues

1. **ngrok tunnel not working**:
   - Check if ngrok is running and accessible
   - Verify the HTTPS URL (GitHub requires HTTPS)
   - Check firewall settings

2. **Functions-framework not starting**:
   ```bash
   # Check if dependencies are installed
   poetry run functions-framework --help

   # Install if missing
   poetry add functions-framework
   ```

## Webhook Management

### Update Webhook

```bash
# Update webhook URL
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/$REPO_NAME/hooks/$HOOK_ID \
  -f config[url]="$NEW_WEBHOOK_URL"
```

### Delete Webhook

```bash
# Delete webhook
gh api \
  --method DELETE \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/$REPO_NAME/hooks/$HOOK_ID
```

### List All Webhooks

```bash
# List all webhooks for the repository
gh api \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/$REPO_NAME/hooks
```

## Testing Strategy

1. **Local Testing Flow**:
   - Start local functions-framework server
   - Start ngrok tunnel
   - Create webhook with ngrok URL
   - Create test PR or trigger event
   - Monitor local logs and ngrok interface

2. **Cloud Function Testing Flow**:
   - Deploy Cloud Function
   - Create webhook with Cloud Function URL
   - Create test PR or trigger event
   - Monitor Cloud Function logs

3. **Automated Testing**:
   - Use `scripts/dev/test-serverless.py` for local testing
   - Use webhook simulation for unit testing
   - Use real repositories for integration testing

## Repository-Specific Setup

### skyral-group/ee-sdlc
```bash
REPO_NAME="skyral-group/ee-sdlc"
# Follow the webhook creation steps above
```

### skyral-group/skyral-ee-security-sandbox
```bash
REPO_NAME="skyral-group/skyral-ee-security-sandbox"
# Follow the webhook creation steps above
```

Both repositories can use the same webhook URL if you want to test with multiple repositories simultaneously.

## Security Considerations

1. **Webhook Secret**: Always use a strong, randomly generated secret
2. **HTTPS Only**: GitHub requires HTTPS for webhook URLs
3. **Signature Validation**: Always validate webhook signatures in production
4. **Rate Limiting**: Implement rate limiting to prevent abuse
5. **Error Handling**: Implement proper error handling and logging

## Next Steps

After setting up webhooks:

1. **Test basic functionality** with the test repositories
2. **Monitor webhook deliveries** in GitHub and your function logs
3. **Iterate on the function** based on real webhook data
4. **Add proper error handling** and monitoring
5. **Deploy to production** with proper security measures
