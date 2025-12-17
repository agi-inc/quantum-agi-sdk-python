"""
Telemetry module for SDK tracing via API proxy.

Sends Sentry telemetry through the AGI API to hide Sentry from SDK users.
"""

import asyncio
import base64
import threading
from collections import deque
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Any, Optional

import httpx

if TYPE_CHECKING:
    from sentry_sdk.envelope import Envelope
    from sentry_sdk.transport import Transport


class ProxyTransport:
    """
    Custom Sentry transport that sends telemetry to the AGI API backend
    instead of directly to Sentry servers.
    """

    def __init__(
        self,
        api_base_url: str,
        api_key: Optional[str] = None,
        batch_size: int = 10,
        flush_interval_seconds: float = 5.0,
    ):
        self._telemetry_endpoint = f"{api_base_url.rstrip('/')}/v1/quantum/telemetry"
        self._api_key = api_key
        self._batch_size = batch_size
        self._flush_interval = flush_interval_seconds
        self._queue: deque[bytes] = deque(maxlen=1000)
        self._lock = threading.Lock()
        self._running = True
        self._flush_thread: Optional[threading.Thread] = None

        # Start background flush thread
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def capture_envelope(self, envelope: "Envelope") -> None:
        """Capture a Sentry envelope for batched sending."""
        if not self._running:
            return

        try:
            # Serialize the envelope
            stream = BytesIO()
            envelope.serialize_into(stream)
            envelope_bytes = stream.getvalue()

            with self._lock:
                self._queue.append(envelope_bytes)

                # Flush if batch size reached
                if len(self._queue) >= self._batch_size:
                    self._flush_batch_sync()
        except Exception:
            # Silently ignore transport errors
            pass

    def _flush_loop(self) -> None:
        """Background thread that periodically flushes the queue."""
        while self._running:
            threading.Event().wait(self._flush_interval)
            if self._running:
                self._flush_batch_sync()

    def _flush_batch_sync(self) -> None:
        """Flush queued envelopes synchronously."""
        with self._lock:
            if not self._queue:
                return

            # Drain the queue
            envelopes = []
            while self._queue:
                envelopes.append(base64.b64encode(self._queue.popleft()).decode("ascii"))

        if not envelopes:
            return

        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            with httpx.Client(timeout=10.0) as client:
                client.post(
                    self._telemetry_endpoint,
                    json={"envelopes": envelopes},
                    headers=headers,
                )
        except Exception:
            # Silently ignore transport errors
            pass

    def flush(self, timeout: float = 2.0) -> None:
        """Flush any remaining envelopes."""
        if not self._running:
            return

        self._flush_batch_sync()

    def close(self) -> None:
        """Stop the transport and flush remaining data."""
        self._running = False
        self.flush()


class TelemetryManager:
    """
    Manages SDK telemetry using Sentry with a proxy transport.

    This class wraps Sentry SDK initialization and provides tracing APIs
    that route through the AGI API backend. Telemetry is always enabled
    and routes through the AGI API to hide Sentry from SDK users.
    """

    # Placeholder DSN - actual forwarding happens server-side via AGI API
    PLACEHOLDER_DSN = "https://placeholder@sentry.internal/0"

    def __init__(
        self,
        api_url: str,
        api_key: Optional[str] = None,
    ):
        self._api_url = api_url
        self._api_key = api_key
        self._transport: Optional[ProxyTransport] = None
        self._transaction: Optional[Any] = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize Sentry with proxy transport."""
        if self._initialized:
            return

        try:
            import sentry_sdk

            self._transport = ProxyTransport(self._api_url, self._api_key)

            sentry_sdk.init(
                dsn=self.PLACEHOLDER_DSN,
                traces_sample_rate=1.0,
                send_default_pii=True,
                transport=self._make_transport_class(),
            )

            self._initialized = True
        except ImportError:
            # sentry-sdk not installed, tracing disabled
            pass
        except Exception:
            # Initialization failed, tracing disabled
            pass

    def _make_transport_class(self) -> type:
        """Create a custom transport class that uses our proxy transport."""
        proxy_transport = self._transport

        try:
            from sentry_sdk.transport import Transport
            from sentry_sdk.envelope import Envelope

            class CustomTransport(Transport):
                def __init__(self, options: dict):
                    pass

                def capture_envelope(self, envelope: Envelope) -> None:
                    if proxy_transport:
                        proxy_transport.capture_envelope(envelope)

                def flush(self, timeout: float, callback: Optional[Any] = None) -> None:
                    if proxy_transport:
                        proxy_transport.flush(timeout)

                def kill(self) -> None:
                    pass

            return CustomTransport
        except ImportError:
            return type("NoOpTransport", (), {})

    def start_transaction(self, name: str, op: str) -> Optional[Any]:
        """Start a new Sentry transaction."""
        if not self._initialized:
            return None

        try:
            import sentry_sdk

            self._transaction = sentry_sdk.start_transaction(name=name, op=op)
            sentry_sdk.configure_scope(lambda scope: setattr(scope, "transaction", self._transaction))
            return self._transaction
        except Exception:
            return None

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag on the current transaction."""
        if self._transaction:
            try:
                self._transaction.set_tag(key, value)
            except Exception:
                pass

    def start_span(self, op: str, description: str) -> Optional[Any]:
        """Start a child span on the current transaction."""
        if not self._transaction:
            return None

        try:
            return self._transaction.start_child(op=op, description=description)
        except Exception:
            return None

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

    def capture_exception(self, exception: Exception) -> None:
        """Capture an exception."""
        if not self._initialized:
            return

        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exception)
        except Exception:
            pass

    def finish_transaction(self, status: str = "ok") -> None:
        """Finish the current transaction."""
        if self._transaction:
            try:
                self._transaction.set_status(status)
                self._transaction.finish()
            except Exception:
                pass
            finally:
                self._transaction = None

    def flush(self, timeout: float = 2.0) -> None:
        """Flush all pending events."""
        if not self._initialized:
            return

        try:
            import sentry_sdk

            sentry_sdk.flush(timeout)
        except Exception:
            pass

        if self._transport:
            self._transport.flush(timeout)

    def close(self) -> None:
        """Close the telemetry manager."""
        self.flush()
        if self._transport:
            self._transport.close()
