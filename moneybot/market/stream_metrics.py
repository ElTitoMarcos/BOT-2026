from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Iterable, Optional


class StreamMetrics:
    def __init__(
        self,
        *,
        streams: Optional[Iterable[str]] = None,
        window_seconds: float = 5.0,
    ) -> None:
        self._lock = threading.Lock()
        self._window_seconds = window_seconds
        self._events: Dict[str, Deque[float]] = {
            stream: deque() for stream in (streams or ())
        }
        self._last_event_ts: Optional[float] = None
        self._open_connections = 0
        self._reconnects = 0
        self._ping_latency_total_ms = 0.0
        self._ping_latency_count = 0

    def record_event(self, stream: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._last_event_ts = now
            events = self._events.setdefault(stream, deque())
            events.append(now)
            self._prune_locked(events, now)

    def connection_open(self) -> None:
        with self._lock:
            self._open_connections += 1

    def connection_closed(self) -> None:
        with self._lock:
            self._open_connections = max(0, self._open_connections - 1)

    def record_reconnect(self) -> None:
        with self._lock:
            self._reconnects += 1

    def record_ping_latency_ms(self, latency_ms: float) -> None:
        if latency_ms < 0:
            return
        with self._lock:
            self._ping_latency_total_ms += latency_ms
            self._ping_latency_count += 1

    def snapshot(self, *, streams: Iterable[str]) -> dict:
        now = time.monotonic()
        with self._lock:
            rates = {
                stream: self._rate_locked(stream, now)
                for stream in streams
            }
            last_age_ms = None
            if self._last_event_ts is not None:
                last_age_ms = (now - self._last_event_ts) * 1000
            avg_latency_ms = None
            if self._ping_latency_count > 0:
                avg_latency_ms = self._ping_latency_total_ms / self._ping_latency_count
            return {
                "event_rate_per_s": rates,
                "ws_connected": self._open_connections > 0,
                "last_ws_event_age_ms": last_age_ms,
                "reconnects": self._reconnects,
                "avg_ping_latency_ms": avg_latency_ms,
            }

    def _rate_locked(self, stream: str, now: float) -> float:
        events = self._events.setdefault(stream, deque())
        self._prune_locked(events, now)
        return len(events) / max(self._window_seconds, 1e-6)

    def _prune_locked(self, events: Deque[float], now: float) -> None:
        cutoff = now - self._window_seconds
        while events and events[0] < cutoff:
            events.popleft()


__all__ = ["StreamMetrics"]
