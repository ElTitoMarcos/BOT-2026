from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


LOGGER = logging.getLogger(__name__)


DEFAULT_ENDPOINT_WEIGHTS: Dict[str, int] = {
    "/api/v3/depth": 1,
    "/api/v3/ticker/price": 1,
    "/api/v3/ticker/24hr": 40,
    "/api/v3/klines": 2,
    "/api/v3/aggTrades": 2,
    "/api/v3/exchangeInfo": 10,
}


def resolve_weight(endpoint: str, params: Optional[Dict[str, Any]] = None) -> int:
    params = params or {}
    if endpoint == "/api/v3/depth":
        limit = int(params.get("limit", 100))
        if limit <= 100:
            return 1
        if limit <= 500:
            return 2
        if limit <= 1000:
            return 5
        return 10
    if endpoint == "/api/v3/ticker/24hr":
        return 1 if params.get("symbol") else 40
    if endpoint == "/api/v3/ticker/price":
        return 1 if params.get("symbol") else 2
    return DEFAULT_ENDPOINT_WEIGHTS.get(endpoint, 1)


@dataclass
class RateLimitMetrics:
    calls_per_minute: int
    weight_per_minute: float


class BinanceRateLimiter:
    def __init__(
        self,
        max_calls_per_minute: int = 1200,
        max_weight_per_minute: int = 1200,
        metrics_log_interval_s: float = 60.0,
    ) -> None:
        self.max_calls_per_minute = max_calls_per_minute
        self.max_weight_per_minute = max_weight_per_minute
        self.metrics_log_interval_s = metrics_log_interval_s
        self._entries: deque[tuple[float, float]] = deque()
        self._total_weight = 0.0
        self._lock = threading.Lock()
        self._last_metrics_log = 0.0

    def acquire(self, weight: float, endpoint: Optional[str] = None) -> RateLimitMetrics:
        while True:
            now = time.monotonic()
            with self._lock:
                self._cleanup(now)
                calls = len(self._entries)
                weight_total = self._total_weight
                if (
                    calls + 1 <= self.max_calls_per_minute
                    and weight_total + weight <= self.max_weight_per_minute
                ):
                    self._entries.append((now, weight))
                    self._total_weight += weight
                    metrics = RateLimitMetrics(
                        calls_per_minute=calls + 1,
                        weight_per_minute=self._total_weight,
                    )
                    self._maybe_log_metrics(now, metrics, endpoint)
                    return metrics
                wait_time = self._next_available_delay(now)
            time.sleep(wait_time)

    def snapshot_metrics(self) -> RateLimitMetrics:
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            return RateLimitMetrics(
                calls_per_minute=len(self._entries),
                weight_per_minute=self._total_weight,
            )

    def _cleanup(self, now: float) -> None:
        while self._entries and now - self._entries[0][0] >= 60:
            _, weight = self._entries.popleft()
            self._total_weight -= weight

    def _next_available_delay(self, now: float) -> float:
        if not self._entries:
            return 0.01
        oldest = self._entries[0][0]
        return max(0.01, 60 - (now - oldest))

    def _maybe_log_metrics(
        self, now: float, metrics: RateLimitMetrics, endpoint: Optional[str]
    ) -> None:
        if now - self._last_metrics_log < self.metrics_log_interval_s:
            return
        self._last_metrics_log = now
        endpoint_info = f" endpoint={endpoint}" if endpoint else ""
        LOGGER.info(
            "RateLimiter métricas: calls/min=%s weight/min=%.0f%s",
            metrics.calls_per_minute,
            metrics.weight_per_minute,
            endpoint_info,
        )


class BinanceRestClient:
    def __init__(
        self,
        base_url: str = "https://api.binance.com",
        rate_limiter: Optional[BinanceRateLimiter] = None,
        session: Optional[requests.Session] = None,
        request_timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter or BinanceRateLimiter()
        self.session = session or requests.Session()
        self.request_timeout = request_timeout

    def get_json(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        weight: Optional[int] = None,
        max_retries: int = 4,
    ) -> Any:
        endpoint_path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        params = params or {}
        weight = weight if weight is not None else resolve_weight(endpoint_path, params)
        url = f"{self.base_url}{endpoint_path}"

        for attempt in range(max_retries + 1):
            self.rate_limiter.acquire(weight, endpoint_path)
            try:
                response = self.session.get(url, params=params, timeout=self.request_timeout)
                if response.status_code in {418, 429} or response.status_code >= 500:
                    raise requests.HTTPError(
                        f"HTTP {response.status_code}: {response.text}",
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                if attempt >= max_retries:
                    raise
                delay = self._backoff_delay(attempt)
                LOGGER.warning(
                    "REST error %s en %s. Reintentando en %.2fs (intento %s/%s).",
                    exc,
                    endpoint_path,
                    delay,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(delay)
        raise RuntimeError("No se pudo completar la solicitud REST.")

    @staticmethod
    def _backoff_delay(attempt: int, base: float = 1.0, cap: float = 20.0) -> float:
        delay = min(cap, base * (2 ** attempt))
        jitter = random.uniform(0, delay * 0.25)
        return delay + jitter
