#!/bin/bash

# Comprehensive RenovateAgent Test Runner
# Tests the polling system with intelligent PR discovery and dashboard monitoring

set -euo pipefail

# Configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TEST_ARTIFACTS_DIR="${SCRIPT_DIR}/test-artifacts"

# Create artifacts directory early
mkdir -p "$TEST_ARTIFACTS_DIR"

readonly LOG_FILE="${TEST_ARTIFACTS_DIR}/test-run-$(date +%Y%m%d-%H%M%S).log"
readonly RESULTS_FILE="${TEST_ARTIFACTS_DIR}/test-results.json"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo -e "${RED}❌ Test run failed with exit code $exit_code${NC}"
        echo -e "${YELLOW}📋 Check logs: $LOG_FILE${NC}"
    fi

    # Kill any background processes
    if [[ -n "${DOCKER_PID:-}" ]]; then
        echo "🧹 Cleaning up Docker process..."
        kill "$DOCKER_PID" 2>/dev/null || true
        wait "$DOCKER_PID" 2>/dev/null || true
    fi

    exit $exit_code
}

trap cleanup EXIT

# Logging function
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case "$level" in
        "INFO")  echo -e "${GREEN}ℹ️  $message${NC}" | tee -a "$LOG_FILE" ;;
        "WARN")  echo -e "${YELLOW}⚠️  $message${NC}" | tee -a "$LOG_FILE" ;;
        "ERROR") echo -e "${RED}❌ $message${NC}" | tee -a "$LOG_FILE" ;;
        "DEBUG") echo -e "${BLUE}🔍 $message${NC}" | tee -a "$LOG_FILE" ;;
        *)       echo -e "$message" | tee -a "$LOG_FILE" ;;
    esac
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
}

# Step functions
step_1_setup() {
    log "INFO" "Step 1: Setting up test environment..."

    # Check required files
    if [[ ! -f ".env" ]]; then
        log "ERROR" ".env file not found. Please create it with your GitHub configuration."
        return 1
    fi

    # Check for GitHub token in .env
    local github_token=$(grep "GITHUB_PERSONAL_ACCESS_TOKEN=" .env | cut -d'=' -f2-)
    if [[ -n "$github_token" && "$github_token" != "ghp_your_token_here" ]]; then
        log "DEBUG" "GitHub token found in .env file"
    else
        log "ERROR" "No valid GitHub token found in .env file"
        return 1
    fi

    log "INFO" "✅ Test environment setup complete"
}

step_2_validate_auth() {
    log "INFO" "Step 2: Validating GitHub authentication..."

    if ! poetry run python scripts/test_github_connection.py > "${TEST_ARTIFACTS_DIR}/auth-check.json" 2>&1; then
        log "ERROR" "GitHub authentication failed"
        cat "${TEST_ARTIFACTS_DIR}/auth-check.json"
        return 1
    fi

    log "INFO" "✅ GitHub authentication successful"
}

step_3_discover_prs() {
    log "INFO" "Step 3: Discovering Renovate PRs..."

    # Temporarily disable exit on error for debugging
    set +e

    # Run PR discovery and capture output
    # Note: Script exits with code 1 when no suitable PRs found, but that's expected
    log "DEBUG" "Running PR discovery script..."
    poetry run python scripts/find_renovate_pr.py > "${TEST_ARTIFACTS_DIR}/pr-discovery-raw.json" 2>&1
    local discovery_exit_code=$?
    log "DEBUG" "PR discovery script exit code: $discovery_exit_code"

    # Extract just the JSON part (starts with '{')
    log "DEBUG" "Extracting JSON from output..."
    if grep -A 1000 '^{' "${TEST_ARTIFACTS_DIR}/pr-discovery-raw.json" > "${TEST_ARTIFACTS_DIR}/pr-discovery.json"; then
        log "DEBUG" "Successfully extracted JSON from PR discovery output"
    else
        log "ERROR" "Failed to extract JSON from PR discovery output"
        log "DEBUG" "Raw output content:"
        head -10 "${TEST_ARTIFACTS_DIR}/pr-discovery-raw.json"
        set -e  # Re-enable exit on error
        return 1
    fi

    # Parse the results with error handling
    log "DEBUG" "Parsing JSON results..."
    local suitable_prs
    local total_renovate_prs

    log "DEBUG" "Parsing suitable PRs..."
    suitable_prs=$(jq -r '.total_suitable_prs // 0' "${TEST_ARTIFACTS_DIR}/pr-discovery.json" 2>/dev/null)
    local jq_exit_1=$?
    log "DEBUG" "jq exit code for suitable PRs: $jq_exit_1, result: $suitable_prs"

    if [[ $jq_exit_1 -eq 0 && -n "$suitable_prs" ]]; then
        log "DEBUG" "Parsed suitable PRs: $suitable_prs"
    else
        log "ERROR" "Failed to parse suitable PRs from JSON"
        suitable_prs="0"
    fi

    log "DEBUG" "Parsing total Renovate PRs..."
    total_renovate_prs=$(jq -r '[.results[].renovate_prs | length] | add // 0' "${TEST_ARTIFACTS_DIR}/pr-discovery.json" 2>/dev/null)
    local jq_exit_2=$?
    log "DEBUG" "jq exit code for total PRs: $jq_exit_2, result: $total_renovate_prs"

    if [[ $jq_exit_2 -eq 0 && -n "$total_renovate_prs" ]]; then
        log "DEBUG" "Parsed total Renovate PRs: $total_renovate_prs"
    else
        log "ERROR" "Failed to parse total Renovate PRs from JSON"
        total_renovate_prs="0"
    fi

    log "INFO" "Found $total_renovate_prs total Renovate PRs, $suitable_prs suitable for approval testing"

    # Store results for later steps
    log "DEBUG" "Storing results to files..."
    echo "$suitable_prs" > "${TEST_ARTIFACTS_DIR}/suitable_pr_count"
    echo "$total_renovate_prs" > "${TEST_ARTIFACTS_DIR}/total_renovate_pr_count"

    if [[ $suitable_prs -gt 0 ]]; then
        log "INFO" "✅ Found PRs suitable for approval testing"
    else
        log "WARN" "⚠️ No PRs suitable for approval testing (all approved or failing CI)"
        log "INFO" "Will test dashboard update functionality instead"
    fi

    # Note: Exit code 1 from find_renovate_pr.py is expected when no suitable PRs found
    if [[ $discovery_exit_code -eq 1 && $total_renovate_prs -gt 0 ]]; then
        log "INFO" "📋 PR discovery completed successfully (found PRs but none suitable for approval testing)"
    elif [[ $discovery_exit_code -ne 0 ]]; then
        log "ERROR" "PR discovery script failed with unexpected error"
        set -e  # Re-enable exit on error
        return 1
    fi

    # Re-enable exit on error
    set -e
    log "DEBUG" "Step 3 completed successfully"
}

step_4_capture_dashboard_before() {
    log "INFO" "Step 4: Capturing dashboard state before test..."

    # Temporarily disable exit on error for debugging
    set +e

    log "DEBUG" "Running dashboard check script..."
    poetry run python scripts/check_dashboard_update.py > "${TEST_ARTIFACTS_DIR}/dashboard-before-raw.json" 2>&1
    local dashboard_exit_code=$?
    log "DEBUG" "Dashboard check exit code: $dashboard_exit_code"

    # Extract just the JSON part (starts with '{')
    if grep -A 1000 '^{' "${TEST_ARTIFACTS_DIR}/dashboard-before-raw.json" > "${TEST_ARTIFACTS_DIR}/dashboard-before.json"; then
        log "DEBUG" "Successfully extracted JSON from dashboard output"
    else
        log "WARN" "Failed to extract JSON from dashboard output, using raw output"
        cp "${TEST_ARTIFACTS_DIR}/dashboard-before-raw.json" "${TEST_ARTIFACTS_DIR}/dashboard-before.json"
    fi

    if [[ $dashboard_exit_code -ne 0 ]]; then
        log "WARN" "Dashboard check had issues (exit code: $dashboard_exit_code), continuing anyway"
    fi

    # Extract key metrics for comparison
    log "DEBUG" "Extracting dashboard metrics..."
    jq -r '.results[] | "\(.repository): \(.pr_entries_count) PR entries, last updated \(.last_updated)"' \
        "${TEST_ARTIFACTS_DIR}/dashboard-before.json" 2>/dev/null | while read -r line; do
        log "DEBUG" "Before: $line"
    done

    # Re-enable exit on error
    set -e

    log "INFO" "✅ Dashboard state captured"
}

step_5_run_polling_system() {
    log "INFO" "Step 5: Running polling system..."

    local suitable_prs=$(cat "${TEST_ARTIFACTS_DIR}/suitable_pr_count")
    local total_prs=$(cat "${TEST_ARTIFACTS_DIR}/total_renovate_pr_count")

    if [[ $suitable_prs -gt 0 ]]; then
        log "INFO" "Testing approval functionality on $suitable_prs suitable PRs"
        local test_duration=120  # 2 minutes for approval testing
    elif [[ $total_prs -gt 0 ]]; then
        log "INFO" "Testing dashboard update functionality with $total_prs total PRs"
        local test_duration=90   # 1.5 minutes for dashboard update testing
    else
        log "INFO" "Testing basic polling functionality (no PRs found)"
        local test_duration=60   # 1 minute for basic testing
    fi

    # Build and run Docker container
    log "INFO" "Building Docker container..."
    if ! docker-compose build --quiet 2>> "$LOG_FILE"; then
        log "ERROR" "Docker build failed"
        return 1
    fi

    log "INFO" "Starting polling system for ${test_duration}s..."
    # Create a temporary override file to use .env
    cat > docker-compose.test.yml << EOF
version: '3.8'
services:
  renovate-agent:
    env_file:
      - path: ./.env
        required: true
    environment:
      # Override with test-specific config
      - ENABLE_POLLING=true
      - DEBUG=true
EOF

    docker-compose -f docker-compose.yml -f docker-compose.test.yml up 2>&1 | tee -a "$LOG_FILE" &
    DOCKER_PID=$!

    # Monitor for specific activity
    local end_time=$(($(date +%s) + test_duration))
    local activity_detected=false

    while [[ $(date +%s) -lt $end_time ]]; do
        sleep 5

        # Check logs for activity
        if tail -n 20 "$LOG_FILE" | grep -q "Processing\|Approved\|Updated dashboard\|Found.*PRs\|Polling cycle"; then
            if [[ "$activity_detected" == "false" ]]; then
                log "INFO" "🔄 Activity detected in polling system"
                activity_detected=true
            fi
        fi
    done

    # Stop the Docker container
    log "INFO" "Stopping polling system..."
    kill "$DOCKER_PID" 2>/dev/null || true
    wait "$DOCKER_PID" 2>/dev/null || true
    unset DOCKER_PID

    docker-compose -f docker-compose.yml -f docker-compose.test.yml down --timeout 10 2>> "$LOG_FILE"
    rm -f docker-compose.test.yml  # Clean up

    if [[ "$activity_detected" == "true" ]]; then
        log "INFO" "✅ Polling system activity detected"
    else
        log "WARN" "⚠️ No obvious polling activity detected in logs"
    fi
}

step_6_capture_dashboard_after() {
    log "INFO" "Step 6: Capturing dashboard state after test..."

    # Wait a moment for any final updates
    sleep 10

    if ! poetry run python scripts/check_dashboard_update.py > "${TEST_ARTIFACTS_DIR}/dashboard-after.json" 2>&1; then
        log "WARN" "Dashboard check had issues, continuing anyway"
    fi

    # Extract key metrics for comparison
    jq -r '.results[] | "\(.repository): \(.pr_entries_count) PR entries, last updated \(.last_updated)"' \
        "${TEST_ARTIFACTS_DIR}/dashboard-after.json" 2>/dev/null | while read -r line; do
        log "DEBUG" "After: $line"
    done

    log "INFO" "✅ Dashboard state captured"
}

step_7_analyze_results() {
    log "INFO" "Step 7: Analyzing test results..."

    local suitable_prs=$(cat "${TEST_ARTIFACTS_DIR}/suitable_pr_count")
    local total_prs=$(cat "${TEST_ARTIFACTS_DIR}/total_renovate_pr_count")

    # Compare dashboard states
    local dashboard_changes=false
    if [[ -f "${TEST_ARTIFACTS_DIR}/dashboard-before.json" && -f "${TEST_ARTIFACTS_DIR}/dashboard-after.json" ]]; then
        if ! diff "${TEST_ARTIFACTS_DIR}/dashboard-before.json" "${TEST_ARTIFACTS_DIR}/dashboard-after.json" > "${TEST_ARTIFACTS_DIR}/dashboard-diff.txt" 2>&1; then
            dashboard_changes=true
            log "INFO" "📊 Dashboard changes detected"
        else
            log "INFO" "📊 No dashboard changes detected"
        fi
    fi

    # Check for specific success indicators in logs
    local approval_success=false
    local dashboard_update_success=false

    if grep -q "PR approved successfully\|approved.*pr_number" "$LOG_FILE"; then
        approval_success=true
        log "INFO" "✅ PR approval functionality confirmed"
    fi

    if grep -q "Updated dashboard\|dashboard.*updated" "$LOG_FILE"; then
        dashboard_update_success=true
        log "INFO" "✅ Dashboard update functionality confirmed"
    fi

    # Determine overall success based on test scenario
    local test_success=false

    if [[ $suitable_prs -gt 0 ]]; then
        # Approval testing scenario
        if [[ "$approval_success" == "true" ]]; then
            test_success=true
            log "INFO" "✅ Approval testing successful"
        else
            log "WARN" "⚠️ No approval activity detected despite suitable PRs"
        fi
    elif [[ $total_prs -gt 0 ]]; then
        # Dashboard update testing scenario
        if [[ "$dashboard_update_success" == "true" || "$dashboard_changes" == "true" ]]; then
            test_success=true
            log "INFO" "✅ Dashboard update testing successful"
        else
            log "WARN" "⚠️ No dashboard updates detected despite existing PRs"
        fi
    else
        # Basic functionality testing
        if grep -q "Starting polling\|Polling.*started\|GitHub authentication successful" "$LOG_FILE"; then
            test_success=true
            log "INFO" "✅ Basic polling functionality confirmed"
        else
            log "WARN" "⚠️ Basic polling functionality issues detected"
        fi
    fi

    echo "{\"test_success\": $test_success, \"scenario\": \"$([[ $suitable_prs -gt 0 ]] && echo "approval" || [[ $total_prs -gt 0 ]] && echo "dashboard" || echo "basic")\"}" > "${TEST_ARTIFACTS_DIR}/test-success.json"

    if [[ "$test_success" == "true" ]]; then
        log "INFO" "✅ Test analysis complete - SUCCESS"
    else
        log "WARN" "⚠️ Test analysis complete - NEEDS INVESTIGATION"
    fi
}

step_8_generate_report() {
    log "INFO" "Step 8: Generating comprehensive test report..."

    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local suitable_prs=$(cat "${TEST_ARTIFACTS_DIR}/suitable_pr_count")
    local total_prs=$(cat "${TEST_ARTIFACTS_DIR}/total_renovate_pr_count")
    local test_success=$(jq -r '.test_success' "${TEST_ARTIFACTS_DIR}/test-success.json" 2>/dev/null || echo "false")
    local test_scenario=$(jq -r '.scenario' "${TEST_ARTIFACTS_DIR}/test-success.json" 2>/dev/null || echo "unknown")

    # Create comprehensive results
    cat > "$RESULTS_FILE" << EOF
{
  "test_run": {
    "timestamp": "$timestamp",
    "success": $test_success,
    "scenario": "$test_scenario",
    "artifacts_dir": "$TEST_ARTIFACTS_DIR"
  },
  "pr_discovery": {
    "total_renovate_prs": $total_prs,
    "suitable_for_approval": $suitable_prs
  },
  "artifacts": {
    "log_file": "$LOG_FILE",
    "pr_discovery": "${TEST_ARTIFACTS_DIR}/pr-discovery.json",
    "dashboard_before": "${TEST_ARTIFACTS_DIR}/dashboard-before.json",
    "dashboard_after": "${TEST_ARTIFACTS_DIR}/dashboard-after.json",
    "auth_check": "${TEST_ARTIFACTS_DIR}/auth-check.json"
  }
}
EOF

    log "INFO" "📋 Test Report Summary:"
    log "INFO" "  Scenario: $test_scenario testing"
    log "INFO" "  Success: $test_success"
    log "INFO" "  Total Renovate PRs: $total_prs"
    log "INFO" "  Suitable for approval: $suitable_prs"
    log "INFO" "  Results: $RESULTS_FILE"
    log "INFO" "  Logs: $LOG_FILE"

    if [[ "$test_success" == "true" ]]; then
        log "INFO" "🎉 All tests completed successfully!"
        return 0
    else
        log "WARN" "⚠️ Some issues detected - check logs for details"
        return 1
    fi
}

# Main execution
main() {
    log "INFO" "🚀 Starting comprehensive RenovateAgent test run..."
    log "INFO" "Timestamp: $(date)"

    step_1_setup
    step_2_validate_auth
    step_3_discover_prs
    step_4_capture_dashboard_before
    step_5_run_polling_system
    step_6_capture_dashboard_after
    step_7_analyze_results
    step_8_generate_report
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
