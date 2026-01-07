from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update(_extract_extra_fields(record))
        return json.dumps(payload, ensure_ascii=False)


def _extract_extra_fields(record: logging.LogRecord) -> Dict[str, Any]:
    reserved = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
    }
    extras = {}
    for key, value in record.__dict__.items():
        if key not in reserved:
            extras[key] = value
    return extras


def configure_logging(
    log_path: str | Path = "logs/moneybot.log",
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    max_bytes = int(os.getenv("LOG_MAX_BYTES", max_bytes))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", backup_count))
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    formatter = JsonFormatter()

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


class ObservabilityStore:
    def __init__(self, max_trades: int = 200) -> None:
        self._lock = threading.Lock()
        self._trades: Deque[Dict[str, Any]] = deque(maxlen=max_trades)
        self._pnl = 0.0
        self._wins = 0
        self._losses = 0
        self._peak = 0.0
        self._max_drawdown = 0.0
        self._risk_metrics: Dict[str, Optional[float | int | bool]] = {
            "open_positions": 0,
            "total_exposure": 0.0,
            "stop_loss_triggered": False,
            "max_open_positions": None,
            "max_exposure_per_symbol": None,
            "global_stop_loss_pct": None,
        }

    def record_trade(self, trade: Dict[str, Any]) -> None:
        with self._lock:
            self._trades.appendleft(trade)

    def record_result(self, pnl_delta: float) -> None:
        with self._lock:
            self._pnl += pnl_delta
            if pnl_delta >= 0:
                self._wins += 1
            else:
                self._losses += 1
            if self._pnl > self._peak:
                self._peak = self._pnl
            drawdown = self._pnl - self._peak
            if drawdown < 0 and abs(drawdown) > self._max_drawdown:
                self._max_drawdown = abs(drawdown)

    def get_trades(self, limit: int) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._trades)[:limit]

    def get_metrics(self) -> Dict[str, Optional[float | int | bool]]:
        with self._lock:
            total = self._wins + self._losses
            winrate = (self._wins / total) if total else None
            metrics: Dict[str, Optional[float | int | bool]] = {
                "pnl": self._pnl,
                "drawdown": self._max_drawdown,
                "winrate": winrate,
            }
            metrics.update(self._risk_metrics)
            return metrics

    def get_pnl_snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {
                "pnl": self._pnl,
                "peak": self._peak,
                "max_drawdown": self._max_drawdown,
            }

    def set_risk_limits(
        self,
        *,
        max_open_positions: Optional[int],
        max_exposure_per_symbol: Optional[float],
        global_stop_loss_pct: Optional[float],
    ) -> None:
        with self._lock:
            self._risk_metrics["max_open_positions"] = max_open_positions
            self._risk_metrics["max_exposure_per_symbol"] = max_exposure_per_symbol
            self._risk_metrics["global_stop_loss_pct"] = global_stop_loss_pct

    def update_risk_snapshot(
        self,
        *,
        open_positions: int,
        total_exposure: float,
        stop_loss_triggered: bool,
    ) -> None:
        with self._lock:
            self._risk_metrics["open_positions"] = open_positions
            self._risk_metrics["total_exposure"] = total_exposure
            self._risk_metrics["stop_loss_triggered"] = stop_loss_triggered


def create_observability_app(bot_app: Any, store: ObservabilityStore):
    from fastapi import FastAPI, Query

    app = FastAPI(title="MoneyBot Observability", docs_url=None, redoc_url=None)

    @app.get("/status")
    def status() -> Dict[str, Any]:
        return bot_app.get_status_snapshot()

    @app.get("/trades")
    def trades(limit: int = Query(50, ge=1, le=1000)) -> Dict[str, Any]:
        return {"trades": store.get_trades(limit)}

    @app.get("/metrics")
    def metrics() -> Dict[str, Optional[float | int | bool]]:
        return store.get_metrics()

    return app


def start_observability_server(bot_app: Any, store: ObservabilityStore) -> Optional[threading.Thread]:
    enabled = os.getenv("OBSERVABILITY_API_ENABLED", "false").lower() in {"1", "true", "yes"}
    if not enabled:
        return None

    host = os.getenv("OBSERVABILITY_API_HOST", "127.0.0.1")
    port = int(os.getenv("OBSERVABILITY_API_PORT", "8001"))

    app = create_observability_app(bot_app, store)

    def run_server() -> None:
        from uvicorn import Config, Server

        config = Config(app=app, host=host, port=port, log_config=None)
        server = Server(config)
        server.run()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread
