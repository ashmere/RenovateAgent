# Local Testing Guide

This guide shows you how to run the Renovate PR Assistant locally for testing. The system now supports **dual-mode operation** with both **polling** (default for local testing) and **webhook** modes available, enhanced with **Phase 2 optimizations** including adaptive intervals, delta detection, intelligent caching, and comprehensive metrics.

## Prerequisites

Before starting, ensure you have:
- **Python 3.12+** installed
- **Poetry** for dependency management (`pip install poetry`)
- **direnv** for environment management (optional but recommended)
- **GitHub account** with access to target repositories

## Quick Start (3 minutes)

### Option 1: Automated Setup (Recommended - Polling Mode with Phase 2 Optimizations)

The setup script handles authentication, validation, and configuration with **intelligent polling as the default** for local testing:

```bash
# 1. Install dependencies
poetry install

# 2. Run automated setup (creates optimized .env file)
poetry run python scripts/setup_local_environment.py

# 3. Start the application in polling mode
poetry run python -m renovate_agent.main
```

The system will automatically use **adaptive polling** with:
- **Smart intervals**: 1-15 minutes based on repository activity
- **Delta detection**: Only process PRs with meaningful changes
- **Intelligent caching**: Reduces API calls by 60-80%
- **Real-time metrics**: Performance monitoring and health scoring

### Option 2: Manual Setup (Advanced Users)

```bash
# 1. Copy and configure environment
cp env.example .env
# Edit .env with your settings

# 2. Validate configuration
poetry run python scripts/validate_config.py

# 3. Start with custom settings
poetry run python -m renovate_agent.main
```

## Environment Configuration

### Recommended Local Testing Configuration (Phase 2 Optimized)

Create a `.env` file with these **optimized** settings for local testing:

```bash
# ================================================================
# OPERATION MODE (Polling Optimized for Local Testing)
# ================================================================
ENABLE_POLLING=true
ENABLE_WEBHOOKS=false

# ================================================================
# PHASE 2 POLLING OPTIMIZATIONS
# ================================================================

# Adaptive Polling (Recommended)
POLLING_ENABLE_ADAPTIVE_INTERVALS=true
POLLING_INTERVAL_MINUTES=2                    # Base interval
POLLING_MAX_CONCURRENT_REPOS=3               # Local resource limits

# Delta Detection (Reduces processing by 70-90%)
POLLING_ENABLE_DELTA_DETECTION=true

# Intelligent Caching (Reduces API calls by 60-80%)
POLLING_ENABLE_CACHING=true
POLLING_CACHE_TTL_SECONDS=300                # 5-minute default cache

# Performance Monitoring
POLLING_METRICS_COLLECTION=true

# ================================================================
# GITHUB AUTHENTICATION (Choose One)
# ================================================================

# Option A: Personal Access Token (Recommended for Local Testing)
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here
GITHUB_APP_ID=0

# Option B: GitHub App (Production-like Testing)
# GITHUB_APP_ID=123456
# GITHUB_APP_PRIVATE_KEY_PATH=/path/to/private-key.pem

# Common Settings
GITHUB_ORGANIZATION=your-org-or-username
GITHUB_WEBHOOK_SECRET=local-test-secret

# ================================================================
# REPOSITORY CONFIGURATION
# ================================================================
POLLING_REPOSITORIES=your-org/test-repo1,your-org/test-repo2
GITHUB_TEST_REPOSITORIES=your-org/test-repo1,your-org/test-repo2

# ================================================================
# RATE LIMITING & PERFORMANCE
# ================================================================
GITHUB_API_RATE_LIMIT=5000                   # Standard GitHub limit
POLLING_RATE_LIMIT_BUFFER=1000              # Safety buffer
POLLING_RATE_LIMIT_THRESHOLD=0.8            # Throttle at 80% usage

# ================================================================
# LOCAL DEVELOPMENT SETTINGS
# ================================================================
DEBUG=true
LOG_LEVEL=DEBUG
HOST=127.0.0.1
PORT=8001
```

## Testing Modes

### 1. Polling Mode Testing (Default - Phase 2 Optimized)

**Features Tested**:
- ✅ Adaptive polling intervals based on repository activity
- ✅ Delta detection for efficient processing
- ✅ Intelligent caching with performance monitoring
- ✅ Real-time metrics and health scoring
- ✅ Rate limit management and adaptive throttling
- ✅ Graceful error handling and recovery

```bash
# Start in polling mode with optimizations
ENABLE_POLLING=true ENABLE_WEBHOOKS=false poetry run python -m renovate_agent.main

# Monitor real-time performance
curl http://localhost:8001/health
```

**Expected Behavior**:
- Starts with 2-minute polling interval
- Adapts to 1-minute for active repositories
- Scales to 5-15 minutes for inactive repositories
- Shows cache hit rates of 80-95% for metadata
- Processes only PRs with actionable changes
- Displays comprehensive metrics in GitHub Issues dashboard

### 2. Webhook Mode Testing (Traditional)

```bash
# Start in webhook mode
ENABLE_POLLING=false ENABLE_WEBHOOKS=true poetry run python -m renovate_agent.main

# Test with webhook simulation
poetry run python scripts/test_renovate_pr_simulation.py --org your-org --repo test-repo --pr 123
```

### 3. Dual Mode Testing (Maximum Reliability)

```bash
# Start both modes simultaneously
ENABLE_POLLING=true ENABLE_WEBHOOKS=true poetry run python -m renovate_agent.main
```

**Features**:
- Webhook events processed immediately
- Polling provides backup coverage
- Automatic deduplication prevents double-processing
- Cross-validation of both event sources

## Phase 2 Features Testing

### Adaptive Polling Testing

Test the intelligent interval adjustment:

```bash
# 1. Create high-activity scenario (multiple PRs)
# 2. Monitor polling intervals in logs
# 3. Verify 1-2 minute intervals for active repos

# 4. Let repository go idle
# 5. Verify interval increases to 5-15 minutes
```

### Delta Detection Testing

Verify efficient change detection:

```bash
# 1. Create a PR and let it be processed
# 2. Make no changes - verify "unchanged" status
# 3. Add commits - verify "updated" status
# 4. Check logs for delta detection results
```

### Caching Performance Testing

Monitor cache effectiveness:

```bash
# Check cache statistics via health endpoint
curl http://localhost:8001/health | jq '.cache_stats'

# Expected: 80-95% hit rate for repository metadata
```

### Metrics Collection Testing

Access comprehensive metrics:

```bash
# View current cycle metrics
curl http://localhost:8001/metrics/current

# View repository performance summary
curl http://localhost:8001/metrics/repositories

# View global performance metrics
curl http://localhost:8001/metrics/global

# View health indicators
curl http://localhost:8001/metrics/health
```

## Advanced Testing Scenarios

### Rate Limiting Simulation

Test adaptive throttling:

```bash
# Set low rate limit for testing
GITHUB_API_RATE_LIMIT=100 poetry run python -m renovate_agent.main

# Monitor adaptive backoff in logs
# Verify graceful degradation
```

### Multi-Repository Testing

Test concurrent processing:

```bash
# Configure multiple repositories
POLLING_REPOSITORIES=org/repo1,org/repo2,org/repo3,org/repo4 poetry run python -m renovate_agent.main

# Monitor concurrent processing
# Verify activity-based prioritization
```

### Error Recovery Testing

Test resilience:

```bash
# 1. Start with invalid repository
# 2. Verify isolated error handling
# 3. Fix configuration
# 4. Verify automatic recovery
```

## Performance Expectations (Phase 2)

### Local Testing Performance
- **Memory Usage**: <30MB for 5-10 repositories
- **API Efficiency**: 60-80% reduction in API calls
- **Processing Speed**: 70-90% fewer unnecessary operations
- **Cache Hit Rates**: 80-95% for metadata, 60-80% for PR lists
- **Polling Intervals**: 1-15 minutes adaptive range

### Monitoring & Debugging

**Health Check Endpoint**:
```bash
curl http://localhost:8001/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "polling_enabled": true,
  "polling_running": true,
  "adaptive_intervals": true,
  "delta_detection": true,
  "caching_enabled": true,
  "cache_stats": {
    "hit_rate_percent": 87.5,
    "cache_size": 42
  },
  "health_score": 95,
  "health_status": "excellent"
}
```

**Real-time Logs**:
```bash
# Watch polling activity
poetry run python -m renovate_agent.main 2>&1 | grep -E "(Polling cycle|Delta detection|Cache)"

# Watch metrics
poetry run python -m renovate_agent.main 2>&1 | grep -E "(Metrics|Health|Performance)"
```

## Troubleshooting

### Common Issues

**1. High API Usage**:
```bash
# Check if caching is enabled
grep POLLING_ENABLE_CACHING .env

# Verify cache hit rates
curl http://localhost:8001/health | jq '.cache_stats.hit_rate_percent'
```

**2. Slow Processing**:
```bash
# Check if delta detection is enabled
grep POLLING_ENABLE_DELTA_DETECTION .env

# Monitor processing efficiency
curl http://localhost:8001/metrics/current | jq '.processing_efficiency'
```

**3. Rate Limiting**:
```bash
# Check rate limit status
curl http://localhost:8001/health | jq '.rate_limiting'

# Verify adaptive throttling
grep "Rate limit" logs.txt
```

### Debug Mode

Enable comprehensive debugging:

```bash
DEBUG=true LOG_LEVEL=DEBUG poetry run python -m renovate_agent.main
```

### Configuration Validation

```bash
# Validate environment configuration
poetry run python scripts/validate_config.py

# Test GitHub connectivity
poetry run python scripts/test_github_connection.py

# Validate repository access
poetry run python scripts/test_repository_access.py
```

## Integration Testing

### End-to-End Testing

Complete workflow validation:

```bash
# 1. Start the system
poetry run python -m renovate_agent.main &

# 2. Run comprehensive test suite
poetry run python scripts/test_polling_system.py

# 3. Verify dashboard updates
# Check GitHub Issues in test repositories

# 4. Validate metrics collection
curl http://localhost:8001/metrics/health
```

### Performance Benchmarking

```bash
# Run performance test suite
poetry run python scripts/benchmark_polling_performance.py

# Expected results:
# - API call reduction: 60-80%
# - Processing efficiency: 70-90%
# - Cache hit rate: 80-95%
# - Health score: >90
```

## Production Migration

### From Webhook to Polling

```bash
# 1. Enable dual mode first
ENABLE_POLLING=true ENABLE_WEBHOOKS=true

# 2. Monitor both modes
curl http://localhost:8001/health

# 3. Gradually disable webhooks
ENABLE_WEBHOOKS=false
```

### Performance Tuning

```bash
# Optimize for your environment
POLLING_INTERVAL_MINUTES=1                 # High-frequency
POLLING_MAX_CONCURRENT_REPOS=10           # High-throughput
POLLING_CACHE_TTL_SECONDS=600             # Extended caching
```

The **Phase 2 optimized polling system** provides enterprise-grade reliability and performance while maintaining the simplicity of local development testing.
