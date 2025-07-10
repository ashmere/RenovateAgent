"""
OpenTelemetry configuration and instrumentation for RenovateAgent.

This module provides comprehensive observability setup including:
- Distributed tracing for request flows
- Metrics collection for performance monitoring
- Structured logging with trace correlation via OpenTelemetry logging instrumentation
- Automatic instrumentation for FastAPI, HTTPX, and other libraries

Note: Uses OpenTelemetry's native logging instrumentation instead of python-json-logger
for consistent structured logging with automatic trace context injection.
"""

import os

import structlog
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

logger = structlog.get_logger(__name__)


class TelemetryConfig:
    """Configuration for OpenTelemetry setup."""

    def __init__(self) -> None:
        """Initialize telemetry configuration from environment variables."""
        # Service identification
        self.service_name = os.getenv("OTEL_SERVICE_NAME", "renovate-agent")
        self.service_version = os.getenv("OTEL_SERVICE_VERSION", "0.6.0")
        self.deployment_environment = os.getenv(
            "OTEL_DEPLOYMENT_ENVIRONMENT", "development"
        )

        # OpenTelemetry endpoints
        self.otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        self.otlp_traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        self.otlp_metrics_endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")

        # Authentication
        self.otlp_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")

        # Feature flags
        self.enable_tracing = os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true"
        self.enable_metrics = (
            os.getenv("OTEL_METRICS_ENABLED", "true").lower() == "true"
        )
        self.enable_console_export = (
            os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true"
        )

        # Instrumentation flags
        self.instrument_fastapi = (
            os.getenv("OTEL_INSTRUMENT_FASTAPI", "true").lower() == "true"
        )
        self.instrument_httpx = (
            os.getenv("OTEL_INSTRUMENT_HTTPX", "true").lower() == "true"
        )
        self.instrument_logging = (
            os.getenv("OTEL_INSTRUMENT_LOGGING", "true").lower() == "true"
        )

    @property
    def resource(self) -> Resource:
        """Create OpenTelemetry resource with service metadata."""
        return Resource.create(
            {
                "service.name": self.service_name,
                "service.version": self.service_version,
                "deployment.environment": self.deployment_environment,
                "service.namespace": "renovate",
            }
        )

    def get_otlp_headers_dict(self) -> dict[str, str]:
        """Parse OTLP headers from string format."""
        if not self.otlp_headers:
            return {}

        headers = {}
        for header in self.otlp_headers.split(","):
            if "=" in header:
                key, value = header.split("=", 1)
                headers[key.strip()] = value.strip()
        return headers


class TelemetryManager:
    """Manages OpenTelemetry instrumentation lifecycle."""

    def __init__(self, config: TelemetryConfig | None = None):
        """Initialize telemetry manager."""
        self.config = config or TelemetryConfig()
        self._tracer_provider: TracerProvider | None = None
        self._meter_provider: MeterProvider | None = None
        self._instrumented = False

    def setup_tracing(self) -> None:
        """Set up distributed tracing."""
        if not self.config.enable_tracing:
            logger.info("Tracing disabled by configuration")
            return

        # Create tracer provider
        self._tracer_provider = TracerProvider(resource=self.config.resource)

        # Add console exporter for development
        if self.config.enable_console_export:
            console_processor = BatchSpanProcessor(ConsoleSpanExporter())
            self._tracer_provider.add_span_processor(console_processor)

        # Add OTLP exporter if endpoint configured
        if self.config.otlp_endpoint or self.config.otlp_traces_endpoint:
            endpoint = self.config.otlp_traces_endpoint or self.config.otlp_endpoint
            headers = self.config.get_otlp_headers_dict()

            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=endpoint,
                    headers=headers,
                )
                otlp_processor = BatchSpanProcessor(otlp_exporter)
                self._tracer_provider.add_span_processor(otlp_processor)
                logger.info("OTLP trace exporter configured", endpoint=endpoint)
            except Exception as e:
                logger.warning("Failed to configure OTLP trace exporter", error=str(e))

        # Set global tracer provider
        trace.set_tracer_provider(self._tracer_provider)
        logger.info("Distributed tracing configured")

    def setup_metrics(self) -> None:
        """Set up metrics collection."""
        if not self.config.enable_metrics:
            logger.info("Metrics disabled by configuration")
            return

        readers = []

        # Add OTLP metrics exporter if endpoint configured
        if self.config.otlp_endpoint or self.config.otlp_metrics_endpoint:
            endpoint = self.config.otlp_metrics_endpoint or self.config.otlp_endpoint
            headers = self.config.get_otlp_headers_dict()

            try:
                otlp_exporter = OTLPMetricExporter(
                    endpoint=endpoint,
                    headers=headers,
                )
                otlp_reader = PeriodicExportingMetricReader(
                    exporter=otlp_exporter,
                    export_interval_millis=30000,  # 30 seconds
                )
                readers.append(otlp_reader)
                logger.info("OTLP metrics exporter configured", endpoint=endpoint)
            except Exception as e:
                logger.warning(
                    "Failed to configure OTLP metrics exporter", error=str(e)
                )

        # Create meter provider
        self._meter_provider = MeterProvider(
            resource=self.config.resource,
            metric_readers=readers,
        )

        # Set global meter provider
        metrics.set_meter_provider(self._meter_provider)
        logger.info("Metrics collection configured")

    def setup_instrumentation(self) -> None:
        """Set up automatic instrumentation."""
        if self._instrumented:
            logger.warning("Instrumentation already set up")
            return

        # FastAPI instrumentation
        if self.config.instrument_fastapi:
            try:
                FastAPIInstrumentor().instrument()
                logger.info("FastAPI instrumentation enabled")
            except Exception as e:
                logger.warning("Failed to instrument FastAPI", error=str(e))

        # HTTPX instrumentation
        if self.config.instrument_httpx:
            try:
                HTTPXClientInstrumentor().instrument()
                logger.info("HTTPX instrumentation enabled")
            except Exception as e:
                logger.warning("Failed to instrument HTTPX", error=str(e))

        # Logging instrumentation
        if self.config.instrument_logging:
            try:
                LoggingInstrumentor().instrument(set_logging_format=True)
                logger.info("Logging instrumentation enabled")
            except Exception as e:
                logger.warning("Failed to instrument logging", error=str(e))

        self._instrumented = True

    def initialize(self) -> None:
        """Initialize complete telemetry stack."""
        logger.info(
            "Initializing telemetry",
            service_name=self.config.service_name,
            environment=self.config.deployment_environment,
            tracing_enabled=self.config.enable_tracing,
            metrics_enabled=self.config.enable_metrics,
        )

        try:
            self.setup_tracing()
            self.setup_metrics()
            self.setup_instrumentation()
            logger.info("Telemetry initialization completed")
        except Exception as e:
            logger.error("Failed to initialize telemetry", error=str(e))
            raise

    def shutdown(self) -> None:
        """Shutdown telemetry providers."""
        logger.info("Shutting down telemetry")

        if self._tracer_provider:
            try:
                self._tracer_provider.shutdown()
                logger.info("Tracer provider shutdown completed")
            except Exception as e:
                logger.warning("Error shutting down tracer provider", error=str(e))

        if self._meter_provider:
            try:
                self._meter_provider.shutdown()
                logger.info("Meter provider shutdown completed")
            except Exception as e:
                logger.warning("Error shutting down meter provider", error=str(e))

    def get_tracer(self, name: str) -> trace.Tracer:
        """Get a tracer for the given name."""
        return trace.get_tracer(name, version=self.config.service_version)

    def get_meter(self, name: str) -> metrics.Meter:
        """Get a meter for the given name."""
        return metrics.get_meter(name, version=self.config.service_version)


# Global telemetry manager instance
_telemetry_manager: TelemetryManager | None = None


def get_telemetry_manager() -> TelemetryManager:
    """Get the global telemetry manager instance."""
    global _telemetry_manager
    if _telemetry_manager is None:
        _telemetry_manager = TelemetryManager()
    return _telemetry_manager


def initialize_telemetry(config: TelemetryConfig | None = None) -> TelemetryManager:
    """Initialize OpenTelemetry with the given configuration."""
    global _telemetry_manager
    _telemetry_manager = TelemetryManager(config)
    _telemetry_manager.initialize()
    return _telemetry_manager


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for the given name."""
    return get_telemetry_manager().get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Get a meter for the given name."""
    return get_telemetry_manager().get_meter(name)


# Custom metrics for RenovateAgent
class RenovateAgentMetrics:
    """Custom metrics for RenovateAgent operations."""

    def __init__(self) -> None:
        """Initialize custom metrics."""
        self.meter = get_meter("renovate_agent.metrics")

        # PR processing metrics
        self.pr_processing_duration = self.meter.create_histogram(
            name="pr_processing_duration_seconds",
            description="Time taken to process a PR",
            unit="s",
        )

        self.pr_processing_counter = self.meter.create_counter(
            name="pr_processing_total",
            description="Total number of PRs processed",
        )

        # GitHub API metrics
        self.github_api_requests = self.meter.create_counter(
            name="github_api_requests_total",
            description="Total GitHub API requests",
        )

        self.github_api_rate_limit = self.meter.create_up_down_counter(
            name="github_api_rate_limit_remaining",
            description="Remaining GitHub API rate limit",
        )

        # Polling metrics
        self.polling_cycle_duration = self.meter.create_histogram(
            name="polling_cycle_duration_seconds",
            description="Time taken for a polling cycle",
            unit="s",
        )

        self.repositories_polled = self.meter.create_counter(
            name="repositories_polled_total",
            description="Total number of repositories polled",
        )

        # Dependency fixing metrics
        self.dependency_fixes_attempted = self.meter.create_counter(
            name="dependency_fixes_attempted_total",
            description="Total dependency fix attempts",
        )

        self.dependency_fixes_successful = self.meter.create_counter(
            name="dependency_fixes_successful_total",
            description="Successful dependency fixes",
        )

    def record_pr_processing(
        self, duration: float, repository: str, status: str
    ) -> None:
        """Record PR processing metrics."""
        attributes = {"repository": repository, "status": status}
        self.pr_processing_duration.record(duration, attributes)
        self.pr_processing_counter.add(1, attributes)

    def record_github_api_request(self, endpoint: str, status_code: int) -> None:
        """Record GitHub API request metrics."""
        attributes = {"endpoint": endpoint, "status_code": str(status_code)}
        self.github_api_requests.add(1, attributes)

    def update_github_rate_limit(self, remaining: int) -> None:
        """Update GitHub API rate limit metrics."""
        self.github_api_rate_limit.add(remaining - self.github_api_rate_limit._value)

    def record_polling_cycle(self, duration: float, repositories_count: int) -> None:
        """Record polling cycle metrics."""
        self.polling_cycle_duration.record(duration)
        self.repositories_polled.add(repositories_count)

    def record_dependency_fix(self, language: str, success: bool) -> None:
        """Record dependency fix attempt."""
        attributes = {"language": language}
        self.dependency_fixes_attempted.add(1, attributes)
        if success:
            self.dependency_fixes_successful.add(1, attributes)


# Global metrics instance
_metrics: RenovateAgentMetrics | None = None


def get_metrics() -> RenovateAgentMetrics:
    """Get the global metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = RenovateAgentMetrics()
    return _metrics
