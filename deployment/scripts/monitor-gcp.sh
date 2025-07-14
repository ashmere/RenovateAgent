#!/bin/bash
# Monitoring script for RenovateAgent Google Cloud Functions deployment

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-}"
FUNCTION_NAME="${GCP_FUNCTION_NAME:-renovate-agent}"
REGION="${GCP_REGION:-europe-west2}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI not found. Please install the Google Cloud SDK"
        exit 1
    fi

    if [ -z "$PROJECT_ID" ]; then
        log_error "PROJECT_ID not set. Set GCP_PROJECT_ID environment variable"
        exit 1
    fi
}

# Get function status
get_function_status() {
    log_info "Getting function status..."

    if gcloud functions describe "$FUNCTION_NAME" --gen2 --region="$REGION" --project="$PROJECT_ID" &> /dev/null; then
        local status=$(gcloud functions describe "$FUNCTION_NAME" --gen2 --region="$REGION" --project="$PROJECT_ID" --format="value(state)")
        local url=$(gcloud functions describe "$FUNCTION_NAME" --gen2 --region="$REGION" --project="$PROJECT_ID" --format="value(serviceConfig.uri)")

        log_info "Function Status: $status"
        log_info "Function URL: $url"
        return 0
    else
        log_error "Function $FUNCTION_NAME not found"
        return 1
    fi
}

# Test function health
test_function_health() {
    log_info "Testing function health..."

    local url=$(gcloud functions describe "$FUNCTION_NAME" --gen2 --region="$REGION" --project="$PROJECT_ID" --format="value(serviceConfig.uri)")

    if [ -z "$url" ]; then
        log_error "Could not get function URL"
        return 1
    fi

    log_debug "Testing health endpoint: $url/health"

    local response=$(curl -s -w "\n%{http_code}" "$url/health" || echo "000")
    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | head -n -1)

    if [ "$http_code" = "200" ]; then
        log_info "✅ Health check passed"
        echo "$body" | jq . 2>/dev/null || echo "$body"
        return 0
    else
        log_error "❌ Health check failed (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Get function logs
get_function_logs() {
    local lines="${1:-50}"

    log_info "Getting function logs (last $lines lines)..."

    gcloud functions logs read "$FUNCTION_NAME" \
        --gen2 \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --limit="$lines" \
        --format="value(timestamp,severity,textPayload)"
}

# Get function metrics
get_function_metrics() {
    log_info "Getting function metrics..."

    # Get invocation count (last 1 hour)
    local invocations=$(gcloud logging read "
        resource.type=cloud_function AND
        resource.labels.function_name=$FUNCTION_NAME AND
        timestamp >= \"$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%SZ')\"
    " --project="$PROJECT_ID" --format="value(timestamp)" | wc -l)

    # Get error count (last 1 hour)
    local errors=$(gcloud logging read "
        resource.type=cloud_function AND
        resource.labels.function_name=$FUNCTION_NAME AND
        severity >= ERROR AND
        timestamp >= \"$(date -u -d '1 hour ago' '+%Y-%m-%dT%H:%M:%SZ')\"
    " --project="$PROJECT_ID" --format="value(timestamp)" | wc -l)

    echo "📊 Function Metrics (last 1 hour):"
    echo "   Invocations: $invocations"
    echo "   Errors: $errors"

    if [ "$invocations" -gt 0 ]; then
        local error_rate=$(echo "scale=2; $errors * 100 / $invocations" | bc -l)
        echo "   Error rate: $error_rate%"
    fi
}

# Watch function logs in real-time
watch_logs() {
    log_info "Watching function logs in real-time..."
    log_info "Press Ctrl+C to stop"

    gcloud functions logs tail "$FUNCTION_NAME" \
        --gen2 \
        --region="$REGION" \
        --project="$PROJECT_ID"
}

# Test webhook endpoint
test_webhook() {
    log_info "Testing webhook endpoint..."

    local url=$(gcloud functions describe "$FUNCTION_NAME" --gen2 --region="$REGION" --project="$PROJECT_ID" --format="value(serviceConfig.uri)")

    if [ -z "$url" ]; then
        log_error "Could not get function URL"
        return 1
    fi

    local test_payload='{
        "action": "opened",
        "pull_request": {
            "number": 999,
            "user": {"login": "renovate[bot]"},
            "head": {"ref": "renovate/test-package"},
            "title": "Test webhook",
            "state": "open"
        },
        "repository": {
            "full_name": "test/repo"
        }
    }'

    log_debug "Testing webhook endpoint: $url"

    local response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$test_payload" \
        "$url" || echo "000")

    local http_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | head -n -1)

    if [ "$http_code" = "200" ]; then
        log_info "✅ Webhook test passed"
        echo "$body" | jq . 2>/dev/null || echo "$body"
        return 0
    else
        log_error "❌ Webhook test failed (HTTP $http_code)"
        echo "$body"
        return 1
    fi
}

# Get function configuration
get_function_config() {
    log_info "Getting function configuration..."

    gcloud functions describe "$FUNCTION_NAME" \
        --gen2 \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --format="yaml(name,serviceConfig.environmentVariables,serviceConfig.secretEnvironmentVariables,serviceConfig.availableMemory,serviceConfig.timeoutSeconds,serviceConfig.maxInstanceCount,serviceConfig.minInstanceCount)"
}

# Show monitoring dashboard
show_dashboard() {
    log_info "Opening monitoring dashboard..."

    local dashboard_url="https://console.cloud.google.com/monitoring/dashboards?project=$PROJECT_ID"

    if command -v open &> /dev/null; then
        open "$dashboard_url"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$dashboard_url"
    else
        log_info "Dashboard URL: $dashboard_url"
    fi
}

# Show function logs in console
show_logs_console() {
    log_info "Opening function logs in console..."

    local logs_url="https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_function%22%0Aresource.labels.function_name%3D%22$FUNCTION_NAME%22?project=$PROJECT_ID"

    if command -v open &> /dev/null; then
        open "$logs_url"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$logs_url"
    else
        log_info "Logs URL: $logs_url"
    fi
}

# Main monitoring function
main() {
    local command="${1:-status}"

    case "$command" in
        "status")
            check_prerequisites
            get_function_status
            echo ""
            test_function_health
            echo ""
            get_function_metrics
            ;;
        "logs")
            check_prerequisites
            get_function_logs "${2:-50}"
            ;;
        "watch")
            check_prerequisites
            watch_logs
            ;;
        "test")
            check_prerequisites
            test_function_health
            echo ""
            test_webhook
            ;;
        "config")
            check_prerequisites
            get_function_config
            ;;
        "dashboard")
            show_dashboard
            ;;
        "console")
            show_logs_console
            ;;
        "metrics")
            check_prerequisites
            get_function_metrics
            ;;
        *)
            show_help
            exit 1
            ;;
    esac
}

# Show help
show_help() {
    cat << EOF
Google Cloud Functions monitoring script for RenovateAgent

Usage: $0 [COMMAND] [OPTIONS]

COMMANDS:
    status          Show function status and health (default)
    logs [lines]    Show function logs (default: 50 lines)
    watch           Watch function logs in real-time
    test            Test function health and webhook endpoints
    config          Show function configuration
    dashboard       Open monitoring dashboard in browser
    console         Open function logs in Google Cloud Console
    metrics         Show function metrics

Environment Variables:
    GCP_PROJECT_ID      GCP Project ID (required)
    GCP_FUNCTION_NAME   Function name (default: renovate-agent)
    GCP_REGION          GCP Region (default: europe-west2)

Examples:
    $0                  # Show status
    $0 logs 100         # Show last 100 log lines
    $0 watch            # Watch logs in real-time
    $0 test             # Test function endpoints
    $0 config           # Show function configuration
    $0 dashboard        # Open monitoring dashboard

EOF
}

# Parse command line arguments
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
    exit 0
fi

# Run main function
main "$@"
