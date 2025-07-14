# RenovateAgent Google Cloud Functions Deployment

This directory contains the deployment configuration and scripts for deploying RenovateAgent to Google Cloud Functions.

## Overview

The deployment includes:

- Google Cloud Functions (Gen 2) for serverless execution
- Secret Manager for secure credential storage
- IAM configuration for proper permissions
- Monitoring and alerting setup
- Terraform infrastructure as code
- Automated deployment scripts

## Prerequisites

1. **Google Cloud SDK**: Install and configure `gcloud` CLI
2. **Terraform**: Install Terraform >= 1.0
3. **Poetry**: For dependency management
4. **GitHub App or Personal Access Token**: For GitHub API access

## Quick Start

### 1. Set up Google Cloud Project

```bash
# Create a new project (optional)
gcloud projects create your-project-id

# Set the project
gcloud config set project your-project-id

# Enable billing (required for Cloud Functions)
gcloud beta billing projects link your-project-id --billing-account=YOUR_BILLING_ACCOUNT
```

### 2. Simple Deployment (using deployment script)

```bash
# Set environment variables
export GCP_PROJECT_ID=your-project-id
export GCP_FUNCTION_NAME=renovate-agent
export GCP_REGION=europe-west2

# Run deployment script
./deployment/scripts/deploy-gcp.sh
```

### 3. Infrastructure as Code (using Terraform)

```bash
# Navigate to Terraform directory
cd deployment/terraform

# Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Initialize Terraform
terraform init

# Plan deployment
terraform plan

# Apply deployment
terraform apply
```

## Configuration

### Environment Variables

The deployment supports the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | Google Cloud Project ID | Required |
| `GCP_FUNCTION_NAME` | Cloud Function name | `renovate-agent` |
| `GCP_REGION` | GCP region | `europe-west2` |
| `GCP_MEMORY` | Memory allocation | `512MB` |
| `GCP_TIMEOUT` | Function timeout | `540s` |
| `GCP_MIN_INSTANCES` | Minimum instances | `0` |
| `GCP_MAX_INSTANCES` | Maximum instances | `10` |

### Secret Management

The deployment uses Google Secret Manager for sensitive credentials:

1. **GitHub Webhook Secret**: `github-webhook-secret`
2. **GitHub App Private Key**: `github-app-private-key`
3. **GitHub Personal Access Token**: `github-personal-access-token` (alternative)

#### Setting up Secrets

```bash
# GitHub webhook secret
echo -n "your-webhook-secret" | gcloud secrets create github-webhook-secret --data-file=-

# GitHub App private key
gcloud secrets create github-app-private-key --data-file=path/to/private-key.pem

# GitHub Personal Access Token (alternative)
echo -n "your-pat-token" | gcloud secrets create github-personal-access-token --data-file=-
```

## Deployment Methods

### Method 1: Deployment Script

The `deploy-gcp.sh` script provides a simple way to deploy the function:

```bash
# Basic deployment
./deployment/scripts/deploy-gcp.sh

# Custom project and function name
./deployment/scripts/deploy-gcp.sh --project my-project --name my-function

# With custom region and memory
./deployment/scripts/deploy-gcp.sh --region europe-west1 --memory 1024MB
```

### Method 2: Terraform

Terraform provides infrastructure as code with better control:

```bash
cd deployment/terraform

# Initialize
terraform init

# Plan
terraform plan -var="project_id=your-project" -var="github_organization=your-org"

# Apply
terraform apply -var="project_id=your-project" -var="github_organization=your-org"
```

### Method 3: Manual Deployment

For custom deployments or troubleshooting:

```bash
# Build deployment package
cd src/
zip -r ../deployment.zip renovate_agent/

# Deploy function
gcloud functions deploy renovate-agent \
  --gen2 \
  --runtime=python311 \
  --region=europe-west2 \
  --source=. \
  --entry-point=renovate_webhook \
  --trigger=http \
  --allow-unauthenticated \
  --memory=512MB \
  --timeout=540s
```

## Monitoring and Logging

### Monitoring Dashboard

The Terraform deployment creates a monitoring dashboard with:
- Function invocations
- Execution duration
- Error rates
- Memory usage

Access at: `https://console.cloud.google.com/monitoring/dashboards/`

### Logging

View function logs:
```bash
gcloud functions logs read renovate-agent --gen2 --region=europe-west2
```

Or use the Cloud Console:
`https://console.cloud.google.com/logs/query`

### Alerting

The deployment includes alert policies for:

- High error rates
- Function timeouts
- Memory usage spikes

Configure notification channels in the monitoring console.

## GitHub Webhook Configuration

After deployment, configure your GitHub webhook:

1. **URL**: Use the function URL from deployment output
2. **Content type**: `application/json`
3. **Secret**: Use the same value stored in Secret Manager
4. **Events**: Select `pull_request`, `check_suite`, `issues`, `push`

Example webhook URL:

```text
https://europe-west2-your-project.cloudfunctions.net/renovate-agent
```

## Testing

### Health Check

Test the deployment with a health check:

```bash
curl https://your-function-url/health
```

Expected response:

```json
{
  "status": "healthy",
  "deployment_mode": "serverless",
  "version": "0.7.0"
}
```

### Webhook Test

Test webhook processing:

```bash
curl -X POST https://your-function-url \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=..." \
  -d '{"action":"opened","pull_request":{"number":1},"repository":{"full_name":"org/repo"}}'
```

### Local Testing

Use the local testing scripts:

```bash
# Test with ngrok
python scripts/dev/test_real_webhooks.py --start-services --suite
```

## Troubleshooting

### Common Issues

1. **Function timeout**: Increase timeout in configuration
2. **Memory issues**: Increase memory allocation
3. **Permission errors**: Check IAM roles and service account permissions
4. **Secret access**: Verify Secret Manager permissions

### Debug Logs

Enable debug logging:

```bash
gcloud functions deploy renovate-agent --set-env-vars LOG_LEVEL=DEBUG
```

### Function Inspection

Inspect function configuration:

```bash
gcloud functions describe renovate-agent --gen2 --region=europe-west2
```

## Cost Optimization

### Recommended Settings

For production:

- **Memory**: 512MB (adjust based on usage)
- **Timeout**: 540s (9 minutes)
- **Min instances**: 0 (cold start is acceptable)
- **Max instances**: 10 (adjust based on webhook volume)

### Cost Monitoring

Monitor costs in the Google Cloud Console:

- Cloud Functions pricing
- Secret Manager usage
- Monitoring costs

## Security

### Best Practices

1. **Use Secret Manager** for all sensitive values
2. **Enable webhook signature validation**
3. **Use least privilege IAM roles**
4. **Monitor function logs** for security issues
5. **Regularly rotate secrets**

### Network Security

The function is deployed with:

- HTTPS-only endpoints
- Webhook signature validation
- Proper CORS configuration
- Rate limiting (if configured)

## Maintenance

### Updates

Update the function:

```bash
# Redeploy with latest code
./deployment/scripts/deploy-gcp.sh

# Or with Terraform
terraform apply
```

### Backup

Important to backup:

- Secret Manager secrets
- Terraform state files
- Environment configuration

### Monitoring

Regular monitoring checks:

- Function error rates
- Execution duration
- Memory usage
- Secret access patterns

## Support

For issues and questions:

1. Check the logs in Cloud Console
2. Review the monitoring dashboard
3. Test with local development setup
4. Consult the main project documentation

## Appendix: Required Google APIs

### Complete API List (Principle of Least Privilege)

The following Google APIs must be enabled in your GCP project to deploy and run RenovateAgent Cloud Function. This list follows the principle of least privilege, enabling only the APIs required for core functionality.

#### Core Function APIs

```bash
# Enable all required APIs at once
gcloud services enable \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iamcredentials.googleapis.com \
  storage.googleapis.com
```

#### Individual API Descriptions

| API | Service Name | Purpose | Required For |
|-----|-------------|---------|--------------|
| **Cloud Functions** | `cloudfunctions.googleapis.com` | Deploy and run serverless functions | Core function deployment |
| **Cloud Build** | `cloudbuild.googleapis.com` | Build and deploy function code | Function deployment process |
| **Secret Manager** | `secretmanager.googleapis.com` | Store GitHub credentials securely | GitHub webhook secret, app private key, PAT |
| **Cloud Logging** | `logging.googleapis.com` | Function logs and log-based metrics | Monitoring, debugging, alerting |
| **Cloud Monitoring** | `monitoring.googleapis.com` | Metrics, dashboards, alerts | Performance monitoring, error alerting |
| **Cloud Resource Manager** | `cloudresourcemanager.googleapis.com` | IAM role management | Service account permissions |
| **IAM Service Account Credentials** | `iamcredentials.googleapis.com` | Service account token creation | Function execution identity |
| **Cloud Storage** | `storage.googleapis.com` | Deployment artifacts storage | Function source code storage |

#### API Enablement Verification

Verify all APIs are enabled:

```bash
# Check all required APIs
gcloud services list --enabled --filter="name:(cloudfunctions.googleapis.com OR cloudbuild.googleapis.com OR secretmanager.googleapis.com OR logging.googleapis.com OR monitoring.googleapis.com OR cloudresourcemanager.googleapis.com OR iamcredentials.googleapis.com OR storage.googleapis.com)" --format="table(name)"
```

#### Security Considerations

1. **No Public APIs**: This list excludes public-facing APIs that aren't required
2. **Minimal Scope**: Only APIs needed for function execution are enabled
3. **Standard Services**: Uses Google's standard service APIs, not beta features
4. **Monitoring Focus**: Includes comprehensive monitoring without exposing unnecessary services

#### Cost Implications

These APIs have the following cost structures:

- **Cloud Functions**: Pay-per-request and compute time
- **Cloud Build**: Free tier available, then pay-per-build-minute
- **Secret Manager**: Pay-per-secret-version and API call
- **Cloud Logging**: Free tier available, then pay-per-GB ingested
- **Cloud Monitoring**: Free tier available, then pay-per-metric
- **Other APIs**: Typically free for management operations

#### Troubleshooting API Issues

If deployment fails with API errors:

```bash
# Check which APIs are missing
gcloud services list --available --filter="name:cloudfunctions.googleapis.com" --format="table(name,title)"

# Enable a specific API
gcloud services enable cloudfunctions.googleapis.com --project=YOUR_PROJECT_ID

# Check API quotas
gcloud services list --enabled --format="table(name,title)" --project=YOUR_PROJECT_ID
```

#### Production Considerations

For production deployments:

- Monitor API quota usage
- Set up billing alerts
- Review API access patterns
- Consider VPC Service Controls for additional security
- Implement least-privilege IAM policies

This API list ensures your GCP project has exactly the permissions needed to run RenovateAgent while maintaining security best practices.
