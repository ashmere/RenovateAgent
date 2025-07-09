"""
Metrics collection and monitoring for the polling system.

This module provides comprehensive metrics tracking for polling operations,
performance monitoring, and health insights.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PollingCycleMetrics:
    """Metrics for a single polling cycle."""

    cycle_id: str
    start_time: datetime
    end_time: datetime | None = None
    repositories_processed: int = 0
    prs_discovered: int = 0
    prs_processed: int = 0
    prs_approved: int = 0
    prs_failed: int = 0
    api_calls_used: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Get cycle duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def processing_rate(self) -> float:
        """Get repositories processed per second."""
        duration = self.duration_seconds
        return self.repositories_processed / duration if duration > 0 else 0.0

    @property
    def cache_hit_rate(self) -> float:
        """Get cache hit rate as percentage."""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0


@dataclass
class RepositoryMetrics:
    """Metrics for a specific repository."""

    repo_name: str
    last_poll_time: datetime | None = None
    total_polls: int = 0
    total_prs_found: int = 0
    total_prs_processed: int = 0
    total_prs_approved: int = 0
    consecutive_empty_polls: int = 0
    activity_score: float = 0.0
    average_poll_duration: float = 0.0
    last_error: str | None = None
    error_count: int = 0

    def update_poll_metrics(
        self, duration: float, prs_found: int, prs_processed: int
    ) -> None:
        """Update metrics after a poll."""
        self.last_poll_time = datetime.now()
        self.total_polls += 1
        self.total_prs_found += prs_found
        self.total_prs_processed += prs_processed

        # Update average duration
        self.average_poll_duration = (
            self.average_poll_duration * (self.total_polls - 1) + duration
        ) / self.total_polls

        # Update consecutive empty polls
        if prs_found == 0:
            self.consecutive_empty_polls += 1
        else:
            self.consecutive_empty_polls = 0


class PerformanceTracker:
    """Tracks performance metrics over time."""

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.cycle_times: deque = deque(maxlen=max_history)
        self.api_call_rates: deque = deque(maxlen=max_history)
        self.error_rates: deque = deque(maxlen=max_history)
        self.pr_processing_rates: deque = deque(maxlen=max_history)

    def record_cycle(self, metrics: PollingCycleMetrics) -> None:
        """Record metrics from a completed cycle."""
        if metrics.end_time:
            self.cycle_times.append(metrics.duration_seconds)
            self.api_call_rates.append(
                metrics.api_calls_used / metrics.duration_seconds
            )
            self.error_rates.append(len(metrics.errors))
            self.pr_processing_rates.append(
                metrics.prs_processed / metrics.duration_seconds
            )

    def get_averages(self) -> dict[str, float]:
        """Get average performance metrics."""
        return {
            "avg_cycle_time": (
                sum(self.cycle_times) / len(self.cycle_times) if self.cycle_times else 0
            ),
            "avg_api_rate": (
                sum(self.api_call_rates) / len(self.api_call_rates)
                if self.api_call_rates
                else 0
            ),
            "avg_error_rate": (
                sum(self.error_rates) / len(self.error_rates) if self.error_rates else 0
            ),
            "avg_pr_rate": (
                sum(self.pr_processing_rates) / len(self.pr_processing_rates)
                if self.pr_processing_rates
                else 0
            ),
        }

    def get_percentiles(self) -> dict[str, float]:
        """Get performance percentiles."""
        if not self.cycle_times:
            return {}

        sorted_times = sorted(self.cycle_times)
        n = len(sorted_times)

        return {
            "p50_cycle_time": sorted_times[n // 2],
            "p90_cycle_time": sorted_times[int(n * 0.9)],
            "p95_cycle_time": sorted_times[int(n * 0.95)],
            "p99_cycle_time": sorted_times[int(n * 0.99)],
        }


class MetricsCollector:
    """
    Central metrics collector for the polling system.

    This class collects, aggregates, and provides access to all
    polling-related metrics and performance data.
    """

    def __init__(self) -> None:
        self.start_time = datetime.now()
        self.repository_metrics: dict[str, RepositoryMetrics] = {}
        self.cycle_history: list[PollingCycleMetrics] = []
        self.current_cycle: PollingCycleMetrics | None = None
        self.performance_tracker = PerformanceTracker()

        # Global counters
        self.total_cycles = 0
        self.total_repositories_processed = 0
        self.total_prs_discovered = 0
        self.total_prs_processed = 0
        self.total_prs_approved = 0
        self.total_api_calls = 0
        self.total_errors = 0

        # Rate limiting metrics
        self.rate_limit_hits = 0
        self.rate_limit_delays = 0
        self.total_rate_limit_delay_seconds = 0.0

    def start_cycle(self, cycle_id: str) -> PollingCycleMetrics:
        """Start a new polling cycle."""
        if self.current_cycle and not self.current_cycle.end_time:
            # End previous cycle if it wasn't properly closed
            self.end_cycle()

        self.current_cycle = PollingCycleMetrics(
            cycle_id=cycle_id, start_time=datetime.now()
        )

        logger.debug("Started metrics collection for cycle", cycle_id=cycle_id)
        return self.current_cycle

    def end_cycle(self) -> PollingCycleMetrics | None:
        """End the current polling cycle."""
        if not self.current_cycle:
            return None

        self.current_cycle.end_time = datetime.now()

        # Update global counters
        self.total_cycles += 1
        self.total_repositories_processed += self.current_cycle.repositories_processed
        self.total_prs_discovered += self.current_cycle.prs_discovered
        self.total_prs_processed += self.current_cycle.prs_processed
        self.total_prs_approved += self.current_cycle.prs_approved
        self.total_api_calls += self.current_cycle.api_calls_used
        self.total_errors += len(self.current_cycle.errors)

        # Record in performance tracker
        self.performance_tracker.record_cycle(self.current_cycle)

        # Store in history (keep last 50 cycles)
        self.cycle_history.append(self.current_cycle)
        if len(self.cycle_history) > 50:
            self.cycle_history.pop(0)

        cycle = self.current_cycle
        self.current_cycle = None

        logger.debug(
            "Completed metrics collection for cycle",
            cycle_id=cycle.cycle_id,
            duration=cycle.duration_seconds,
            repositories=cycle.repositories_processed,
            prs_processed=cycle.prs_processed,
        )

        return cycle

    def record_repository_poll(
        self,
        repo_name: str,
        duration: float,
        prs_found: int,
        prs_processed: int,
        error: str | None = None,
    ) -> None:
        """Record metrics for a repository poll."""
        if repo_name not in self.repository_metrics:
            self.repository_metrics[repo_name] = RepositoryMetrics(repo_name=repo_name)

        repo_metrics = self.repository_metrics[repo_name]
        repo_metrics.update_poll_metrics(duration, prs_found, prs_processed)

        if error:
            repo_metrics.last_error = error
            repo_metrics.error_count += 1

        # Update current cycle metrics
        if self.current_cycle:
            self.current_cycle.repositories_processed += 1
            self.current_cycle.prs_discovered += prs_found
            self.current_cycle.prs_processed += prs_processed
            if error:
                self.current_cycle.errors.append(f"{repo_name}: {error}")

    def record_pr_approval(self, repo_name: str, pr_number: str, success: bool) -> None:
        """Record PR approval metrics."""
        if self.current_cycle:
            if success:
                self.current_cycle.prs_approved += 1
            else:
                self.current_cycle.prs_failed += 1

        if repo_name in self.repository_metrics and success:
            self.repository_metrics[repo_name].total_prs_approved += 1

    def record_api_call(self, count: int = 1) -> None:
        """Record API call usage."""
        if self.current_cycle:
            self.current_cycle.api_calls_used += count

    def record_cache_access(self, hit: bool) -> None:
        """Record cache access metrics."""
        if self.current_cycle:
            if hit:
                self.current_cycle.cache_hits += 1
            else:
                self.current_cycle.cache_misses += 1

    def record_rate_limit_hit(self, delay_seconds: float = 0.0) -> None:
        """Record rate limit hit."""
        self.rate_limit_hits += 1
        if delay_seconds > 0:
            self.rate_limit_delays += 1
            self.total_rate_limit_delay_seconds += delay_seconds

    def get_current_cycle_metrics(self) -> dict[str, Any] | None:
        """Get metrics for the current cycle."""
        if not self.current_cycle:
            return None

        return {
            "cycle_id": self.current_cycle.cycle_id,
            "start_time": self.current_cycle.start_time.isoformat(),
            "duration_seconds": (
                datetime.now() - self.current_cycle.start_time
            ).total_seconds(),
            "repositories_processed": self.current_cycle.repositories_processed,
            "prs_discovered": self.current_cycle.prs_discovered,
            "prs_processed": self.current_cycle.prs_processed,
            "prs_approved": self.current_cycle.prs_approved,
            "prs_failed": self.current_cycle.prs_failed,
            "api_calls_used": self.current_cycle.api_calls_used,
            "cache_hit_rate": self.current_cycle.cache_hit_rate,
            "errors": len(self.current_cycle.errors),
        }

    def get_repository_summary(self) -> dict[str, dict[str, Any]]:
        """Get summary metrics for all repositories."""
        summary = {}
        for repo_name, metrics in self.repository_metrics.items():
            summary[repo_name] = {
                "total_polls": metrics.total_polls,
                "total_prs_found": metrics.total_prs_found,
                "total_prs_processed": metrics.total_prs_processed,
                "total_prs_approved": metrics.total_prs_approved,
                "consecutive_empty_polls": metrics.consecutive_empty_polls,
                "activity_score": metrics.activity_score,
                "average_poll_duration": metrics.average_poll_duration,
                "last_poll": (
                    metrics.last_poll_time.isoformat()
                    if metrics.last_poll_time
                    else None
                ),
                "last_error": metrics.last_error,
                "error_count": metrics.error_count,
            }
        return summary

    def get_global_summary(self) -> dict[str, Any]:
        """Get global polling metrics summary."""
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        performance_averages = self.performance_tracker.get_averages()
        performance_percentiles = self.performance_tracker.get_percentiles()

        return {
            "uptime_seconds": uptime_seconds,
            "uptime_hours": uptime_seconds / 3600,
            "total_cycles": self.total_cycles,
            "total_repositories_processed": self.total_repositories_processed,
            "total_prs_discovered": self.total_prs_discovered,
            "total_prs_processed": self.total_prs_processed,
            "total_prs_approved": self.total_prs_approved,
            "total_api_calls": self.total_api_calls,
            "total_errors": self.total_errors,
            "approval_rate": (
                (self.total_prs_approved / self.total_prs_processed * 100)
                if self.total_prs_processed > 0
                else 0
            ),
            "error_rate": (
                (self.total_errors / self.total_cycles * 100)
                if self.total_cycles > 0
                else 0
            ),
            "rate_limiting": {
                "total_hits": self.rate_limit_hits,
                "total_delays": self.rate_limit_delays,
                "total_delay_seconds": self.total_rate_limit_delay_seconds,
                "average_delay": (
                    self.total_rate_limit_delay_seconds / self.rate_limit_delays
                    if self.rate_limit_delays > 0
                    else 0
                ),
            },
            "performance": {
                **performance_averages,
                **performance_percentiles,
            },
        }

    def get_health_indicators(self) -> dict[str, Any]:
        """Get health indicators for monitoring."""
        recent_cycles = self.cycle_history[-10:] if self.cycle_history else []
        recent_errors = sum(len(cycle.errors) for cycle in recent_cycles)
        recent_avg_duration = (
            sum(cycle.duration_seconds for cycle in recent_cycles) / len(recent_cycles)
            if recent_cycles
            else 0
        )

        # Health scoring (0-100)
        health_score = 100.0

        # Reduce score based on recent error rate
        if recent_cycles:
            error_rate = recent_errors / len(recent_cycles)
            health_score -= min(error_rate * 20, 50)  # Max 50 point reduction

        # Reduce score based on rate limiting
        if self.rate_limit_hits > 0:
            hit_rate = self.rate_limit_hits / max(self.total_cycles, 1)
            health_score -= min(hit_rate * 30, 30)  # Max 30 point reduction

        # Determine health status
        if health_score >= 90:
            status = "excellent"
        elif health_score >= 75:
            status = "good"
        elif health_score >= 50:
            status = "fair"
        elif health_score >= 25:
            status = "poor"
        else:
            status = "critical"

        return {
            "status": status,
            "health_score": max(0, health_score),
            "recent_error_count": recent_errors,
            "recent_avg_duration": recent_avg_duration,
            "active_repositories": len(self.repository_metrics),
            "last_cycle_time": (
                self.cycle_history[-1].end_time.isoformat()
                if self.cycle_history and self.cycle_history[-1].end_time
                else None
            ),
        }


# Global metrics collector instance
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics() -> None:
    """Reset the global metrics collector."""
    global _metrics_collector
    _metrics_collector = MetricsCollector()
