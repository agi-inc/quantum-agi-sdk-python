"""
Telemetry module for SDK tracing via Sentry.

Sends telemetry directly to Sentry for real-time observability.
"""

from datetime import datetime
from typing import Any, Optional


# Sentry DSN for the agent-api-server project
SENTRY_DSN = "https://1bb09da3f54d24a607294f1c070a8d48@o4509402314309632.ingest.us.sentry.io/4510377562865664"


class TelemetryManager:
    """
    Manages SDK telemetry using Sentry.

    This class wraps Sentry SDK initialization and provides event-based
    logging APIs that send events directly to Sentry for real-time observability.
    """

    def __init__(self):
        self._initialized = False

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

            self._initialized = True
        except ImportError:
            # sentry-sdk not installed, tracing disabled
            pass
        except Exception:
            # Initialization failed, tracing disabled
            pass

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
