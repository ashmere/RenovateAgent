#!/bin/bash

# Comprehensive Real-World Test Runner
# Intelligent testing with dynamic PR discovery and full validation
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_header() {
    echo -e "${BLUE}$1${NC}"
    echo "==============================================================="
}

# Cleanup function
cleanup() {
    log_info "Cleaning up test resources..."

    # Stop and remove Docker container if running
    if docker ps -q --filter "name=renovate-agent-test" | grep -q .; then
        docker stop renovate-agent-test >/dev/null 2>&1 || true
    fi

    if docker ps -aq --filter "name=renovate-agent-test" | grep -q .; then
        docker rm renovate-agent-test >/dev/null 2>&1 || true
    fi

    # Remove temporary files
    rm -f .env.test pr_discovery.json dashboard_check.json test_results.json
}

# Set up trap for cleanup
trap cleanup EXIT

# Main test execution
main() {
    log_header "🚀 RenovateAgent Phase 2 - Comprehensive Real-World Test"

    # Step 1: Validate environment and authentication
    log_info "Step 1: Validating environment and GitHub authentication..."

    if [ ! -f ".env" ]; then
        log_error ".env file not found"
        log_info "Please ensure .env contains your GitHub credentials"
        exit 1
    fi

    if ! grep -q "GITHUB_PERSONAL_ACCESS_TOKEN" .env; then
        log_error "GITHUB_PERSONAL_ACCESS_TOKEN not found in .env"
        log_info "Please add your GitHub PAT to .env file"
        exit 1
    fi

    # Test GitHub connection using existing script
    log_info "Testing GitHub connection..."
    if ! poetry run python scripts/test_github_connection.py >/dev/null 2>&1; then
        log_error "GitHub authentication failed"
        log_info "Please check your GitHub credentials in .env"
        exit 1
    fi
    log_success "GitHub authentication verified"

    # Step 2: Discover suitable Renovate PRs
    log_info "Step 2: Discovering suitable Renovate PRs for testing..."

    if ! poetry run python scripts/find_renovate_pr.py > pr_discovery.json 2>/tmp/pr_discovery.log; then
        log_error "Failed to discover Renovate PRs"
        cat /tmp/pr_discovery.log
        exit 1
    fi

    # Parse PR discovery results
    suitable_count=$(jq -r '.total_suitable_prs' pr_discovery.json)
    test_repos=$(jq -r '.test_repositories[]' pr_discovery.json | tr '\n' ',' | sed 's/,$//')

    if [ "$suitable_count" -eq 0 ]; then
        log_warning "No suitable Renovate PRs found for testing"
        log_info "Suitable PRs must be:"
        log_info "  - Created by Renovate"
        log_info "  - Not already approved"
        log_info "  - Have passing CI checks"

        # Show what we found for debugging
        log_info "Found repositories and their PRs:"
        jq -r '.results[] | "  \(.repository): \(.renovate_prs | length) Renovate PRs"' pr_discovery.json

        exit 1
    fi

    # Get the first suitable PR for testing
    target_repo=$(jq -r '.results[] | select(.suitable_prs | length > 0) | .suitable_prs[0].repository' pr_discovery.json)
    target_pr=$(jq -r '.results[] | select(.suitable_prs | length > 0) | .suitable_prs[0].number' pr_discovery.json)
    target_title=$(jq -r '.results[] | select(.suitable_prs | length > 0) | .suitable_prs[0].title' pr_discovery.json)
    target_url=$(jq -r '.results[] | select(.suitable_prs | length > 0) | .suitable_prs[0].url' pr_discovery.json)

    log_success "Found $suitable_count suitable PRs across repositories: $test_repos"
    log_info "Selected for testing: $target_repo#$target_pr"
    log_info "PR Title: $target_title"
    log_info "PR URL: $target_url"

    # Step 3: Capture initial dashboard state
    log_info "Step 3: Capturing initial dashboard state..."

    if ! poetry run python scripts/check_dashboard_update.py > dashboard_check_before.json 2>/tmp/dashboard_before.log; then
        log_warning "Could not check initial dashboard state"
        cat /tmp/dashboard_before.log
    else
        log_success "Initial dashboard state captured"
    fi

    # Step 4: Configure and run the polling system
    log_info "Step 4: Configuring polling system for testing..."

    # Create test-specific environment
    cat > .env.test << EOF
# Load base configuration
$(cat .env)

# Override for polling test - target specific repository
ENABLE_POLLING=true
ENABLE_WEBHOOKS=false
POLLING_INTERVAL_MINUTES=0.5
POLLING_REPOSITORIES=$target_repo
GITHUB_TEST_REPOSITORIES=$target_repo
DASHBOARD_CREATION_MODE=renovate-only

# Phase 2 optimizations enabled
ENABLE_ADAPTIVE_INTERVALS=true
ENABLE_DELTA_DETECTION=true
ENABLE_CACHING=true
CACHE_TTL_SECONDS=60

# Debug and monitoring
DEBUG=true
ENABLE_METRICS_COLLECTION=true
EOF

    log_success "Test environment configured for repository: $target_repo"

    # Step 5: Build and run the system
    log_info "Step 5: Building and starting RenovateAgent..."

    if ! docker build -t renovate-agent:test . >/dev/null 2>&1; then
        log_error "Docker build failed"
        exit 1
    fi
    log_success "Docker image built successfully"

    # Start the container
    log_info "Starting polling system container..."
    docker run --name renovate-agent-test \
        --env-file .env.test \
        -p 8000:8000 \
        -d \
        renovate-agent:test

    # Wait for startup and check health
    log_info "Waiting for system startup..."
    sleep 10

    # Check if container is running
    if ! docker ps --filter "name=renovate-agent-test" --format "table {{.Names}}" | grep -q "renovate-agent-test"; then
        log_error "Container failed to start"
        docker logs renovate-agent-test
        exit 1
    fi

    # Health check
    if ! curl -s http://localhost:8000/health >/dev/null; then
        log_error "Health check failed"
        docker logs renovate-agent-test
        exit 1
    fi
    log_success "System started and healthy"

    # Step 6: Monitor for processing activity
    log_info "Step 6: Monitoring for PR processing (waiting up to 3 minutes)..."
    log_info "Target: $target_repo PR #$target_pr"
    log_info "==============================================================="

    # Monitor logs for specific activity
    monitor_duration=180  # 3 minutes
    start_time=$(date +%s)
    pr_detected=false
    approval_attempted=false

    while [ $(($(date +%s) - start_time)) -lt $monitor_duration ]; do
        # Get recent logs
        recent_logs=$(docker logs renovate-agent-test --since 30s 2>&1)

        # Check for PR detection
        if echo "$recent_logs" | grep -q "pr_number=$target_pr"; then
            if [ "$pr_detected" = false ]; then
                log_success "Target PR #$target_pr detected in processing"
                pr_detected=true
            fi
        fi

        # Check for approval attempts
        if echo "$recent_logs" | grep -q "PR approved successfully.*pr_number=$target_pr"; then
            log_success "PR #$target_pr approved successfully!"
            approval_attempted=true
            break
        elif echo "$recent_logs" | grep -q "approval.*failed.*pr_number=$target_pr"; then
            log_warning "PR #$target_pr approval failed (check logs for reason)"
            approval_attempted=true
            break
        elif echo "$recent_logs" | grep -q "Skipping approval.*pr_number=$target_pr"; then
            log_warning "PR #$target_pr approval skipped (normal business rules)"
            approval_attempted=true
            break
        fi

        # Show progress
        echo -n "."
        sleep 5
    done
    echo

    # Step 7: Validate results
    log_info "Step 7: Validating test results..."

    # Check dashboard updates
    log_info "Checking for dashboard updates..."
    if poetry run python scripts/check_dashboard_update.py > dashboard_check_after.json 2>/tmp/dashboard_after.log; then

        # Compare before and after
        if [ -f dashboard_check_before.json ]; then
            before_updated=$(jq -r '.results[0].recently_updated // false' dashboard_check_before.json)
            after_updated=$(jq -r '.results[0].recently_updated // false' dashboard_check_after.json)

            if [ "$after_updated" = "true" ] && [ "$before_updated" = "false" ]; then
                log_success "Dashboard was updated during test run"
            elif [ "$after_updated" = "true" ]; then
                log_warning "Dashboard shows recent activity (but may have been recent before test)"
            else
                log_warning "Dashboard was not updated recently"
            fi
        else
            if [ "$(jq -r '.results[0].recently_updated // false' dashboard_check_after.json)" = "true" ]; then
                log_success "Dashboard shows recent activity"
            fi
        fi

        # Show dashboard URLs
        jq -r '.results[] | "Dashboard: \(.dashboard_url)"' dashboard_check_after.json | while read line; do
            log_info "$line"
        done
    else
        log_warning "Could not verify dashboard updates"
    fi

    # Final system logs analysis
    log_info "Analyzing system logs for test results..."
    docker logs renovate-agent-test > test_run.log 2>&1

    # Count key activities
    total_polls=$(grep -c "Polling cycle completed" test_run.log || echo "0")
    prs_processed=$(grep -c "Processing.*PR" test_run.log || echo "0")
    approvals=$(grep -c "PR approved successfully" test_run.log || echo "0")

    log_info "System Activity Summary:"
    log_info "  - Total polling cycles: $total_polls"
    log_info "  - PRs processed: $prs_processed"
    log_info "  - Successful approvals: $approvals"

    # Step 8: Generate final test report
    log_info "Step 8: Generating test report..."

    # Create comprehensive test results
    cat > test_results.json << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "test_target": {
        "repository": "$target_repo",
        "pr_number": $target_pr,
        "pr_title": "$target_title",
        "pr_url": "$target_url"
    },
    "discovery": $(cat pr_discovery.json),
    "dashboard_before": $(cat dashboard_check_before.json 2>/dev/null || echo "null"),
    "dashboard_after": $(cat dashboard_check_after.json 2>/dev/null || echo "null"),
    "system_activity": {
        "pr_detected": $pr_detected,
        "approval_attempted": $approval_attempted,
        "total_polls": $total_polls,
        "prs_processed": $prs_processed,
        "approvals": $approvals
    },
    "test_duration_seconds": $(($(date +%s) - start_time))
}
EOF

    # Final verdict
    log_header "🎯 Test Results Summary"

    if [ "$pr_detected" = true ] && [ "$approval_attempted" = true ]; then
        log_success "Test PASSED: System successfully detected and processed target PR"
        log_info "Target PR: $target_url"

        if [ "$approvals" -gt 0 ]; then
            log_success "✅ PR was approved during test"
        else
            log_warning "⚠️  PR was processed but not approved (may be due to business rules)"
        fi

        log_info "💾 Detailed results saved to: test_results.json"
        log_info "📋 Full system logs saved to: test_run.log"

        exit 0
    else
        log_error "Test FAILED: System did not properly process target PR"

        if [ "$pr_detected" = false ]; then
            log_error "❌ Target PR was not detected during polling"
        fi

        if [ "$approval_attempted" = false ]; then
            log_error "❌ No approval attempt was made"
        fi

        log_info "🔍 Check test_run.log for detailed system behavior"
        log_info "💾 Partial results saved to: test_results.json"

        exit 1
    fi
}

# Script execution
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    main "$@"
fi
