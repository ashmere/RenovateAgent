#!/bin/bash
# Google Cloud Functions deployment script for RenovateAgent
# This script deploys the serverless RenovateAgent to Google Cloud Functions

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
FUNCTION_NAME="${GCP_FUNCTION_NAME:-renovate-agent}"
REGION="${GCP_REGION:-europe-west2}"
MEMORY="${GCP_MEMORY:-512MB}"
TIMEOUT="${GCP_TIMEOUT:-540s}"
RUNTIME="${GCP_RUNTIME:-python313}"
ENTRY_POINT="${GCP_ENTRY_POINT:-renovate_webhook}"
MIN_INSTANCES="${GCP_MIN_INSTANCES:-0}"
MAX_INSTANCES="${GCP_MAX_INSTANCES:-3}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI not found. Please install the Google Cloud SDK"
        exit 1
    fi

    # Check if user is authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" &> /dev/null; then
        log_error "Not authenticated with gcloud. Run 'gcloud auth login'"
        exit 1
    fi

    # Check if project ID is set
    if [ -z "$PROJECT_ID" ]; then
        log_error "PROJECT_ID not set. Set GCP_PROJECT_ID environment variable or run 'gcloud config set project YOUR_PROJECT_ID'"
        exit 1
    fi

    # Check if APIs are enabled
    log_info "Checking required APIs..."
    if ! gcloud services list --enabled --filter="name:cloudfunctions.googleapis.com" --format="value(name)" &> /dev/null; then
        log_warn "Cloud Functions API not enabled. Enabling..."
        gcloud services enable cloudfunctions.googleapis.com --project="$PROJECT_ID"
    fi

    if ! gcloud services list --enabled --filter="name:cloudbuild.googleapis.com" --format="value(name)" &> /dev/null; then
        log_warn "Cloud Build API not enabled. Enabling..."
        gcloud services enable cloudbuild.googleapis.com --project="$PROJECT_ID"
    fi

    log_info "Prerequisites check passed"
}

# Build deployment package
build_package() {
    log_info "Building deployment package..."

    # Create temp directory for deployment
    DEPLOY_DIR=$(mktemp -d)
    log_info "Using deployment directory: $DEPLOY_DIR"

    # Copy source code
    cp -r src/renovate_agent "$DEPLOY_DIR/"

    # Copy requirements
    cp pyproject.toml "$DEPLOY_DIR/"

    # Create requirements.txt from pyproject.toml
    cd "$DEPLOY_DIR"
    poetry export --without-hashes --format=requirements.txt > requirements.txt

    # Create main.py entry point
    cat > main.py << 'EOF'
"""
Google Cloud Functions entry point for RenovateAgent.
"""
from renovate_agent.serverless.main import renovate_webhook

# Export the function for Cloud Functions
__all__ = ["renovate_webhook"]
EOF

    log_info "Deployment package built in $DEPLOY_DIR"
    echo "$DEPLOY_DIR"
}

# Deploy to Cloud Functions
deploy_function() {
    local deploy_dir="$1"

    log_info "Deploying to Google Cloud Functions..."
    log_info "Project: $PROJECT_ID"
    log_info "Function: $FUNCTION_NAME"
    log_info "Region: $REGION"
    log_info "Runtime: $RUNTIME"

    cd "$deploy_dir"

    # Deploy function
    gcloud functions deploy "$FUNCTION_NAME" \
        --gen2 \
        --runtime="$RUNTIME" \
        --region="$REGION" \
        --source=. \
        --entry-point="$ENTRY_POINT" \
        --memory="$MEMORY" \
        --timeout="$TIMEOUT" \
        --min-instances="$MIN_INSTANCES" \
        --max-instances="$MAX_INSTANCES" \
        --trigger=http \
        --allow-unauthenticated \
        --set-env-vars="DEPLOYMENT_MODE=serverless" \
        --project="$PROJECT_ID"

    log_info "Function deployed successfully"
}

# Get function URL
get_function_url() {
    log_info "Getting function URL..."

    URL=$(gcloud functions describe "$FUNCTION_NAME" \
        --gen2 \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --format="value(serviceConfig.uri)")

    log_info "Function URL: $URL"
    echo "$URL"
}

# Test deployment
test_deployment() {
    local url="$1"

    log_info "Testing deployment..."

    # Test health endpoint
    if curl -s -f "$url/health" > /dev/null; then
        log_info "Health check passed"
    else
        log_error "Health check failed"
        return 1
    fi

    # Test webhook endpoint
    local test_payload='{"action":"opened","pull_request":{"number":999,"user":{"login":"renovate[bot]"}},"repository":{"full_name":"test/repo"}}'

    if curl -s -f -X POST -H "Content-Type: application/json" -d "$test_payload" "$url" > /dev/null; then
        log_info "Webhook endpoint test passed"
    else
        log_warn "Webhook endpoint test failed (might be due to missing environment variables)"
    fi
}

# Main deployment function
main() {
    log_info "Starting Google Cloud Functions deployment..."

    # Check prerequisites
    check_prerequisites

    # Build package
    DEPLOY_DIR=$(build_package)

    # Deploy function
    deploy_function "$DEPLOY_DIR"

    # Get function URL
    FUNCTION_URL=$(get_function_url)

    # Test deployment
    test_deployment "$FUNCTION_URL"

    # Cleanup
    rm -rf "$DEPLOY_DIR"

    log_info "Deployment completed successfully!"
    log_info "Function URL: $FUNCTION_URL"
    log_info "Configure your GitHub webhook to: $FUNCTION_URL"
}

# Show help
show_help() {
    cat << EOF
Google Cloud Functions deployment script for RenovateAgent

Usage: $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -p, --project PROJECT   GCP Project ID
    -n, --name NAME         Function name (default: renovate-agent)
    -r, --region REGION     GCP Region (default: europe-west2)
    -m, --memory MEMORY     Memory allocation (default: 512MB)
    -t, --timeout TIMEOUT   Timeout (default: 540s)

Environment Variables:
    GCP_PROJECT_ID          GCP Project ID
    GCP_FUNCTION_NAME       Function name
    GCP_REGION              GCP Region
    GCP_MEMORY              Memory allocation
    GCP_TIMEOUT             Timeout
    GCP_MIN_INSTANCES       Minimum instances
    GCP_MAX_INSTANCES       Maximum instances

Examples:
    $0                      # Deploy with defaults
    $0 -p my-project        # Deploy to specific project
    $0 -n my-function       # Deploy with custom function name

    # Set environment variables
    export GCP_PROJECT_ID=my-project
    export GCP_FUNCTION_NAME=renovate-webhook
    $0

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -p|--project)
            PROJECT_ID="$2"
            shift 2
            ;;
        -n|--name)
            FUNCTION_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -m|--memory)
            MEMORY="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Run main function
main
