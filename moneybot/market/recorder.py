from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

import websocket

from moneybot.config import DEPTH_SPEED
from moneybot.datastore import DataStore, normalize_timestamp
from moneybot.market.stream_metrics import StreamMetrics

LOGGER = logging.getLogger(__name__)


@dataclass
class RecorderConnection:
    streams: List[str]
    thread: threading.Thread
    stop_event: threading.Event


class BinanceHFRecorder:
    def __init__(
        self,
        *,
        datastore: Optional[DataStore] = None,
        ws_url: str = "wss://stream.binance.com:9443/stream",
        max_streams_per_connection: int = 200,
        depth_speed: str = DEPTH_SPEED,
        metrics: Optional[StreamMetrics] = None,
    ) -> None:
        self.datastore = datastore or DataStore()
        self.ws_url = ws_url
        self.max_streams_per_connection = max_streams_per_connection
        self.depth_speed = depth_speed
        self._connections: list[RecorderConnection] = []
        self._lock = threading.Lock()
        self._metrics = metrics

    def start(self, symbols: Iterable[str]) -> None:
        streams = self._build_streams(symbols)
        chunks = [
            streams[i : i + self.max_streams_per_connection]
            for i in range(0, len(streams), self.max_streams_per_connection)
        ]
        with self._lock:
            for chunk in chunks:
                stop_event = threading.Event()
                thread = threading.Thread(
                    target=self._run_connection,
                    args=(chunk, stop_event),
                    daemon=True,
                )
                self._connections.append(
                    RecorderConnection(streams=chunk, thread=thread, stop_event=stop_event)
                )
                thread.start()

    def stop(self) -> None:
        with self._lock:
            connections = list(self._connections)
            self._connections = []
        for connection in connections:
            connection.stop_event.set()
        for connection in connections:
            if connection.thread.is_alive():
                connection.thread.join(timeout=5)

    def _build_streams(self, symbols: Iterable[str]) -> List[str]:
        streams: List[str] = []
        for symbol in symbols:
            lower = symbol.lower()
            streams.extend(
                [
                    f"{lower}@aggTrade",
                    f"{lower}@depth@{self.depth_speed}",
                    f"{lower}@bookTicker",
                ]
            )
        return streams

    def _run_connection(self, streams: List[str], stop_event: threading.Event) -> None:
        query = "/".join(streams)
        url = f"{self.ws_url}?streams={query}&timeUnit=MICROSECOND"
        last_error_message: Optional[str] = None
        last_error_ts = 0.0

        def safe_callback(name: str, func, *args) -> None:
            try:
                func(*args)
            except websocket.WebSocketConnectionClosedException:
                LOGGER.debug("WS callback %s ignorado: stream cerrado", name)
            except Exception as exc:
                LOGGER.warning("WS callback %s fallo: %s", name, exc)

        def on_error(_ws: websocket.WebSocketApp, error: object) -> None:
            nonlocal last_error_message, last_error_ts
            if stop_event.is_set():
                return
            message = str(error)
            normalized = message.strip().lower()
            now = time.monotonic()
            if message == last_error_message and (now - last_error_ts) < 5.0:
                return
            last_error_message = message
            last_error_ts = now
            if normalized in {"stream is closed", "connection is already closed"} or isinstance(
                error, websocket.WebSocketConnectionClosedException
            ):
                LOGGER.debug("WS cerrado inesperado (%s streams): %s", len(streams), message)
                return
            LOGGER.warning("WS error (%s streams): %s", len(streams), message)

        def on_open(_ws: websocket.WebSocketApp) -> None:
            if self._metrics:
                self._metrics.connection_open()

        def on_message(_ws: websocket.WebSocketApp, message: str) -> None:
            self._handle_message(message)

        def on_close(_ws: websocket.WebSocketApp, status: int, reason: str) -> None:
            LOGGER.info("WS cerrado (%s streams): %s %s", len(streams), status, reason)

        def on_ping(_ws: websocket.WebSocketApp, message: str) -> None:
            LOGGER.debug("WS ping %s", message)

        def on_pong(_ws: websocket.WebSocketApp, message: str) -> None:
            LOGGER.debug("WS pong %s", message)

        while not stop_event.is_set():
            ws = websocket.WebSocketApp(
                url,
                on_open=lambda _ws: safe_callback("open", on_open, _ws),
                on_message=lambda _ws, message: safe_callback("message", on_message, _ws, message),
                on_error=on_error,
                on_close=lambda _ws, status, reason: safe_callback(
                    "close",
                    on_close,
                    _ws,
                    status,
                    reason,
                ),
                on_ping=lambda _ws, message: safe_callback("ping", on_ping, _ws, message),
                on_pong=lambda _ws, message: safe_callback("pong", on_pong, _ws, message),
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
            if self._metrics:
                self._metrics.connection_closed()
            if stop_event.is_set():
                break
            delay = 1.0 + random.uniform(0, 2.0)
            time.sleep(delay)

    def _handle_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            LOGGER.debug("Mensaje WS inválido")
            return
        try:
            data = payload.get("data", payload)
            stream = payload.get("stream")
            stream_type = self._infer_stream(stream)
            event_type = data.get("e") or stream_type
            if event_type == "depthUpdate":
                event_type = "depth"
            if stream_type in {"depth", "bookTicker", "aggTrade"}:
                event_type = stream_type
            symbol = data.get("s")
            if not event_type or not symbol:
                return
            if self._metrics and stream_type:
                self._metrics.record_event(stream_type)
            event_ts = normalize_timestamp(data.get("T") or data.get("E"))
            if event_ts <= 0:
                event_ts = int(time.time() * 1000)
            self.datastore.write_event(symbol, event_type, data, event_ts)
        except Exception as exc:
            LOGGER.debug("Error procesando mensaje WS: %s", exc)

    @staticmethod
    def _infer_stream(stream_name: Optional[str]) -> Optional[str]:
        if not stream_name:
            return None
        if "@" not in stream_name:
            return None
        return stream_name.split("@", 1)[1].split("@")[0]


__all__ = ["BinanceHFRecorder"]
