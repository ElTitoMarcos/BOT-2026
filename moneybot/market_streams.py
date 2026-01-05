from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

import websocket


LOGGER = logging.getLogger(__name__)


@dataclass
class StreamSnapshot:
    payload: dict
    updated_at: float


class BinanceStreamCache:
    def __init__(
        self,
        ws_url: str = "wss://stream.binance.com:9443/ws",
        max_age_seconds: float = 2.5,
    ) -> None:
        self.ws_url = ws_url.rstrip("/")
        self.max_age_seconds = max_age_seconds
        self._order_books: Dict[str, StreamSnapshot] = {}
        self._prices: Dict[str, StreamSnapshot] = {}
        self._connections: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def ensure_order_book_stream(self, symbol: str, depth: int = 10) -> None:
        stream = f"{symbol.lower()}@depth{depth}@100ms"
        self._ensure_stream(stream, self._handle_order_book(symbol))

    def ensure_price_stream(self, symbol: str) -> None:
        stream = f"{symbol.lower()}@ticker"
        self._ensure_stream(stream, self._handle_price(symbol))

    def get_order_book(self, symbol: str) -> Optional[dict]:
        with self._lock:
            snapshot = self._order_books.get(symbol)
            if not snapshot:
                return None
            if time.monotonic() - snapshot.updated_at > self.max_age_seconds:
                return None
            return snapshot.payload

    def get_price(self, symbol: str) -> Optional[float]:
        with self._lock:
            snapshot = self._prices.get(symbol)
            if not snapshot:
                return None
            if time.monotonic() - snapshot.updated_at > self.max_age_seconds:
                return None
            return snapshot.payload.get("price")

    def _ensure_stream(self, stream: str, handler) -> None:
        with self._lock:
            if stream in self._connections:
                return
            thread = threading.Thread(
                target=self._run_stream,
                args=(stream, handler),
                daemon=True,
                name=f"ws_{stream}",
            )
            self._connections[stream] = thread
            thread.start()

    def _run_stream(self, stream: str, handler) -> None:
        url = f"{self.ws_url}/{stream}"
        while True:
            ws = websocket.WebSocketApp(
                url,
                on_message=lambda _ws, message: handler(message),
                on_error=lambda _ws, error: LOGGER.warning(
                    "WebSocket error en %s: %s", stream, error
                ),
                on_close=lambda _ws, status_code, reason: LOGGER.info(
                    "WebSocket cerrado %s (%s): %s", stream, status_code, reason
                ),
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
            delay = 1.0 + random.uniform(0, 1.5)
            time.sleep(delay)

    def _handle_order_book(self, symbol: str):
        def _inner(message: str) -> None:
            try:
                data = json.loads(message)
                payload = data.get("data", data)
                bids = payload.get("bids") or payload.get("b")
                asks = payload.get("asks") or payload.get("a")
                if not bids or not asks:
                    return
                snapshot = {"bids": bids, "asks": asks}
                with self._lock:
                    self._order_books[symbol] = StreamSnapshot(
                        payload=snapshot, updated_at=time.monotonic()
                    )
            except json.JSONDecodeError:
                LOGGER.warning("Mensaje WS inválido para order book %s", symbol)
        return _inner

    def _handle_price(self, symbol: str):
        def _inner(message: str) -> None:
            try:
                data = json.loads(message)
                payload = data.get("data", data)
                price_raw = payload.get("c") or payload.get("p")
                if price_raw is None:
                    return
                price = float(price_raw)
                with self._lock:
                    self._prices[symbol] = StreamSnapshot(
                        payload={"price": price}, updated_at=time.monotonic()
                    )
            except (json.JSONDecodeError, ValueError):
                LOGGER.warning("Mensaje WS inválido para precio %s", symbol)
        return _inner
