#!/bin/bash
# Setup secrets in Google Secret Manager for RenovateAgent

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
WEBHOOK_SECRET_ID="${GCP_WEBHOOK_SECRET_ID:-github-webhook-secret}"
APP_PRIVATE_KEY_SECRET_ID="${GCP_APP_PRIVATE_KEY_SECRET_ID:-github-app-private-key}"
PAT_SECRET_ID="${GCP_PAT_SECRET_ID:-github-personal-access-token}"

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
        log_error "PROJECT_ID not set. Set GCP_PROJECT_ID environment variable"
        exit 1
    fi

    # Enable Secret Manager API
    log_info "Enabling Secret Manager API..."
    gcloud services enable secretmanager.googleapis.com --project="$PROJECT_ID"

    log_info "Prerequisites check passed"
}

# Create or update secret
create_or_update_secret() {
    local secret_id="$1"
    local secret_value="$2"
    local description="$3"

    log_info "Processing secret: $secret_id"

    # Check if secret exists
    if gcloud secrets describe "$secret_id" --project="$PROJECT_ID" &> /dev/null; then
        log_info "Secret $secret_id already exists, adding new version"
        echo -n "$secret_value" | gcloud secrets versions add "$secret_id" --data-file=- --project="$PROJECT_ID"
    else
        log_info "Creating new secret: $secret_id"
        echo -n "$secret_value" | gcloud secrets create "$secret_id" --data-file=- --project="$PROJECT_ID"
    fi

    log_info "✅ Secret $secret_id configured successfully"
}

# Create secret from file
create_secret_from_file() {
    local secret_id="$1"
    local file_path="$2"
    local description="$3"

    if [ ! -f "$file_path" ]; then
        log_error "File not found: $file_path"
        return 1
    fi

    log_info "Processing secret from file: $secret_id"

    # Check if secret exists
    if gcloud secrets describe "$secret_id" --project="$PROJECT_ID" &> /dev/null; then
        log_info "Secret $secret_id already exists, adding new version"
        gcloud secrets versions add "$secret_id" --data-file="$file_path" --project="$PROJECT_ID"
    else
        log_info "Creating new secret: $secret_id"
        gcloud secrets create "$secret_id" --data-file="$file_path" --project="$PROJECT_ID"
    fi

    log_info "✅ Secret $secret_id configured successfully"
}

# Setup webhook secret
setup_webhook_secret() {
    log_info "Setting up GitHub webhook secret..."

    if [ -n "$GITHUB_WEBHOOK_SECRET" ]; then
        create_or_update_secret "$WEBHOOK_SECRET_ID" "$GITHUB_WEBHOOK_SECRET" "GitHub webhook secret"
    else
        log_warn "GITHUB_WEBHOOK_SECRET not set. Please provide it:"
        read -s -p "Enter GitHub webhook secret: " webhook_secret
        echo
        create_or_update_secret "$WEBHOOK_SECRET_ID" "$webhook_secret" "GitHub webhook secret"
    fi
}

# Setup GitHub App private key
setup_app_private_key() {
    log_info "Setting up GitHub App private key..."

    if [ -n "$GITHUB_APP_PRIVATE_KEY_PATH" ] && [ -f "$GITHUB_APP_PRIVATE_KEY_PATH" ]; then
        create_secret_from_file "$APP_PRIVATE_KEY_SECRET_ID" "$GITHUB_APP_PRIVATE_KEY_PATH" "GitHub App private key"
    else
        log_warn "GITHUB_APP_PRIVATE_KEY_PATH not set or file not found. Please provide path:"
        read -p "Enter path to GitHub App private key file: " key_path
        if [ -f "$key_path" ]; then
            create_secret_from_file "$APP_PRIVATE_KEY_SECRET_ID" "$key_path" "GitHub App private key"
        else
            log_error "File not found: $key_path"
            return 1
        fi
    fi
}

# Setup GitHub Personal Access Token
setup_personal_access_token() {
    log_info "Setting up GitHub Personal Access Token..."

    if [ -n "$GITHUB_PERSONAL_ACCESS_TOKEN" ]; then
        create_or_update_secret "$PAT_SECRET_ID" "$GITHUB_PERSONAL_ACCESS_TOKEN" "GitHub Personal Access Token"
    else
        log_warn "GITHUB_PERSONAL_ACCESS_TOKEN not set. Please provide it:"
        read -s -p "Enter GitHub Personal Access Token: " pat_token
        echo
        create_or_update_secret "$PAT_SECRET_ID" "$pat_token" "GitHub Personal Access Token"
    fi
}

# List secrets
list_secrets() {
    log_info "Listing configured secrets..."

    echo "Configured secrets in project $PROJECT_ID:"
    gcloud secrets list --project="$PROJECT_ID" --filter="name:($WEBHOOK_SECRET_ID OR $APP_PRIVATE_KEY_SECRET_ID OR $PAT_SECRET_ID)" --format="table(name,createTime,updateTime)"
}

# Test secret access
test_secret_access() {
    local secret_id="$1"

    log_info "Testing access to secret: $secret_id"

    if gcloud secrets versions access latest --secret="$secret_id" --project="$PROJECT_ID" &> /dev/null; then
        log_info "✅ Secret $secret_id is accessible"
        return 0
    else
        log_error "❌ Secret $secret_id is not accessible"
        return 1
    fi
}

# Main setup function
main() {
    log_info "Starting Google Secret Manager setup for RenovateAgent..."

    # Check prerequisites
    check_prerequisites

    # Setup secrets based on arguments
    case "${1:-all}" in
        "webhook")
            setup_webhook_secret
            ;;
        "app-key")
            setup_app_private_key
            ;;
        "pat")
            setup_personal_access_token
            ;;
        "all")
            setup_webhook_secret

            # Ask user which authentication method to use
            echo ""
            log_info "Choose authentication method:"
            echo "1) GitHub App (recommended for production)"
            echo "2) Personal Access Token (easier for development)"
            read -p "Enter choice (1 or 2): " auth_choice

            case "$auth_choice" in
                1)
                    setup_app_private_key
                    ;;
                2)
                    setup_personal_access_token
                    ;;
                *)
                    log_error "Invalid choice. Please run again."
                    exit 1
                    ;;
            esac
            ;;
        "list")
            list_secrets
            exit 0
            ;;
        "test")
            test_secret_access "$WEBHOOK_SECRET_ID"
            test_secret_access "$APP_PRIVATE_KEY_SECRET_ID"
            test_secret_access "$PAT_SECRET_ID"
            exit 0
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac

    # List configured secrets
    echo ""
    list_secrets

    # Test access
    echo ""
    log_info "Testing secret access..."
    test_secret_access "$WEBHOOK_SECRET_ID"
    if [ "$auth_choice" = "1" ]; then
        test_secret_access "$APP_PRIVATE_KEY_SECRET_ID"
    else
        test_secret_access "$PAT_SECRET_ID"
    fi

    log_info "Secret setup completed successfully!"
    echo ""
    log_info "Next steps:"
    echo "1. Deploy the function: ./deployment/scripts/deploy-gcp.sh"
    echo "2. Configure GitHub webhook with the function URL"
    echo "3. Test the webhook integration"
}

# Show help
show_help() {
    cat << EOF
Google Secret Manager setup script for RenovateAgent

Usage: $0 [COMMAND]

COMMANDS:
    all         Setup all secrets (default)
    webhook     Setup GitHub webhook secret only
    app-key     Setup GitHub App private key only
    pat         Setup GitHub Personal Access Token only
    list        List configured secrets
    test        Test secret access

Environment Variables:
    GCP_PROJECT_ID                  GCP Project ID (required)
    GITHUB_WEBHOOK_SECRET          GitHub webhook secret
    GITHUB_APP_PRIVATE_KEY_PATH    Path to GitHub App private key file
    GITHUB_PERSONAL_ACCESS_TOKEN   GitHub Personal Access Token

Examples:
    $0                  # Setup all secrets interactively
    $0 webhook          # Setup webhook secret only
    $0 list             # List configured secrets
    $0 test             # Test secret access

    # With environment variables
    export GCP_PROJECT_ID=my-project
    export GITHUB_WEBHOOK_SECRET=my-secret
    $0 webhook

EOF
}

# Parse command line arguments
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
    exit 0
fi

# Run main function
main "$@"
