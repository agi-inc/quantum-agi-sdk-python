"""
Telemetry module for SDK tracing via Sentry.

Sends telemetry directly to Sentry for real-time observability.
Supports transactions and spans for end-to-end waterfall tracking.
"""

from datetime import datetime
from typing import Any, Optional, Dict, Callable, TypeVar

T = TypeVar('T')

# Sentry DSN for the agent-api-server project
SENTRY_DSN = "https://1bb09da3f54d24a607294f1c070a8d48@o4509402314309632.ingest.us.sentry.io/4510377562865664"

# Type alias for Sentry spans (used when sentry_sdk is available)
Span = Any
Transaction = Any
SpanStatus = str  # 'ok' | 'internal_error' | 'cancelled' | 'unknown'


class TelemetryManager:
    """
    Manages SDK telemetry using Sentry.

    This class wraps Sentry SDK initialization and provides event-based
    logging APIs that send events directly to Sentry for real-time observability.
    Supports transactions and child spans for end-to-end waterfall tracking.
    """

    def __init__(self):
        self._initialized = False
        self._sentry_sdk = None

    def initialize(self) -> None:
        """Initialize Sentry SDK only if AGI_TELEMETRY_ENABLED=true."""
        if self._initialized:
            return

        import os
        if os.environ.get("AGI_TELEMETRY_ENABLED") != "true":
            return

        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=SENTRY_DSN,
                traces_sample_rate=1.0,
                send_default_pii=True,
            )

            self._sentry_sdk = sentry_sdk
            self._initialized = True
        except ImportError:
            # sentry-sdk not installed, tracing disabled
            pass
        except Exception:
            # Initialization failed, tracing disabled
            pass

    def is_enabled(self) -> bool:
        """Check if telemetry is enabled and initialized."""
        return self._initialized

    def start_transaction(
        self,
        name: str,
        operation: str,
        tags: Optional[Dict[str, str]] = None
    ) -> Optional[Transaction]:
        """
        Start a new transaction for tracking a multi-step operation.
        Used for agent.step.{N} transactions.

        Args:
            name: Transaction name (e.g., "agent.step.1")
            operation: Operation type (e.g., "agent.step")
            tags: Optional tags to attach to the transaction

        Returns:
            The transaction span, or None if telemetry is disabled
        """
        if not self._initialized or not self._sentry_sdk:
            return None

        try:
            transaction = self._sentry_sdk.start_transaction(
                name=name,
                op=operation,
            )

            if transaction and tags:
                for key, value in tags.items():
                    transaction.set_tag(key, value)

            return transaction
        except Exception:
            return None

    def start_span(
        self,
        operation: str,
        description: str,
        parent_span: Optional[Span] = None
    ) -> Optional[Span]:
        """
        Start a child span within a transaction.
        Used for tracking sub-operations like screenshot capture, inference calls, action execution.

        Args:
            operation: Operation type (e.g., "screenshot.capture", "http.client", "action.click")
            description: Human-readable description
            parent_span: Optional parent span to nest under

        Returns:
            The child span, or None if telemetry is disabled
        """
        if not self._initialized or not self._sentry_sdk:
            return None

        try:
            if parent_span:
                span = parent_span.start_child(
                    op=operation,
                    description=description,
                )
            else:
                span = self._sentry_sdk.start_span(
                    op=operation,
                    description=description,
                )
            return span
        except Exception:
            return None

    def set_span_status(self, span: Optional[Span], status: SpanStatus) -> None:
        """
        Set the status of a span.

        Args:
            span: The span to update
            status: The status to set ('ok', 'internal_error', 'cancelled', 'unknown')
        """
        if not span:
            return

        try:
            span.set_status(status)
        except Exception:
            pass

    def set_span_data(self, span: Optional[Span], key: str, value: Any) -> None:
        """
        Set data on a span.

        Args:
            span: The span to update
            key: Data key
            value: Data value
        """
        if not span:
            return

        try:
            span.set_data(key, value)
        except Exception:
            pass

    def set_span_tag(self, span: Optional[Span], key: str, value: str) -> None:
        """
        Set a tag on a span.

        Args:
            span: The span to update
            key: Tag key
            value: Tag value
        """
        if not span:
            return

        try:
            span.set_tag(key, value)
        except Exception:
            pass

    def finish_span(self, span: Optional[Span]) -> None:
        """
        Finish a span, recording its duration.

        Args:
            span: The span to finish
        """
        if not span:
            return

        try:
            span.finish()
        except Exception:
            pass

    def get_trace_headers(self) -> Dict[str, str]:
        """
        Get Sentry trace headers for distributed tracing.
        These headers should be added to outgoing HTTP requests.

        Returns:
            Dict with sentry-trace and baggage headers, or empty dict if unavailable
        """
        if not self._initialized or not self._sentry_sdk:
            return {}

        try:
            headers = {}

            # Get current span for trace context
            current_span = self._sentry_sdk.get_current_span()
            if current_span:
                trace_context = current_span.to_traceparent()
                if trace_context:
                    headers["sentry-trace"] = trace_context

                # Get baggage
                baggage = current_span.to_baggage()
                if baggage:
                    headers["baggage"] = baggage

            return headers
        except Exception:
            return {}

    def add_breadcrumb(self, category: str, message: str, level: str = "info", data: Optional[dict] = None) -> None:
        """Add a breadcrumb to the current scope."""
        if not self._initialized:
            return

        try:
            import sentry_sdk

            sentry_sdk.add_breadcrumb(
                category=category,
                message=message,
                level=level,
                data=data or {},
            )
        except Exception:
            pass

    def capture_message(self, message: str, level: str = "info", tags: Optional[dict] = None, extras: Optional[dict] = None) -> None:
        """Capture a message event and send it to Sentry immediately."""
        if not self._initialized:
            return

        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                if tags:
                    for key, value in tags.items():
                        scope.set_tag(key, str(value) if value is not None else "")
                if extras:
                    for key, value in extras.items():
                        scope.set_extra(key, str(value) if value is not None else "")

                sentry_sdk.capture_message(message, level=level)
        except Exception:
            pass

    def capture_exception(self, exception: Exception) -> None:
        """Capture an exception."""
        if not self._initialized:
            return

        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exception)
        except Exception:
            pass

    def flush(self, timeout: float = 2.0) -> None:
        """Flush all pending events."""
        if not self._initialized:
            return

        try:
            import sentry_sdk

            sentry_sdk.flush(timeout)
        except Exception:
            pass

    def close(self) -> None:
        """Close the telemetry manager."""
        self.flush()
