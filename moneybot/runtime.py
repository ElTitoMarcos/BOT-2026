from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from moneybot.backtest.replay import ReplayEngine
from moneybot.backtest.simulator import ExecutionSimulator
from moneybot.config import LOOKBACK_DAYS_DEFAULT
from moneybot.datastore import DataStore
from moneybot.market.recorder import BinanceHFRecorder
from moneybot.market.stream_metrics import StreamMetrics
from moneybot.market_streams import BinanceStreamCache
from moneybot.market.testnet_stream_cache import TestnetStreamCache
from moneybot.observability import ObservabilityStore
from moneybot.strategy.accumulation_strategy import AccumulationStrategy
from moneybot.strategy.base_strategy import BaseStrategy
from moneybot.strategy.simple_strategy import SimReplayStrategy


@dataclass
class SimConfig:
    symbols: list[str]
    lookback_days: int
    initial_balance: float
    fee_rate: float
    slippage_bps: float


class BotRuntime:
    def __init__(
        self,
        mode: Optional[str] = None,
        observability: Optional[ObservabilityStore] = None,
    ) -> None:
        self.is_running = False
        self.mode = (mode or os.getenv("BOT_MODE", "SIM")).upper()
        self.last_update_ts: Optional[float] = None
        self.stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._uptime_start = time.monotonic()
        self._observability = observability or ObservabilityStore()
        self._ws_metrics = StreamMetrics(
            streams=("aggTrade", "depth", "bookTicker"),
            window_seconds=5.0,
        )

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self.stop_event.clear()
            self.is_running = True
            self.last_update_ts = time.time()
            targets = {
                "SIM": self._run_sim_pipeline,
                "LIVE": self._run_live_engine,
                "TESTNET": self._run_testnet_engine,
                "HIST": self._run_historical_engine,
            }
            target = targets.get(self.mode, self._run_sim_pipeline)
            self._thread = threading.Thread(target=target, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self.stop_event.set()
            thread = self._thread
            self._thread = None

        if thread and thread.is_alive():
            thread.join(timeout=5)
        self.is_running = False

    def set_mode(self, mode: str) -> None:
        self.mode = mode.upper()

    def status(self) -> dict:
        now = time.time()
        last_update_iso = None
        last_update_age_s = None
        if self.last_update_ts is not None:
            last_update_iso = datetime.fromtimestamp(
                self.last_update_ts, tz=timezone.utc
            ).isoformat()
            last_update_age_s = max(0.0, now - self.last_update_ts)
        ws_snapshot = self._ws_metrics.snapshot(
            streams=("aggTrade", "depth", "bookTicker")
        )
        return {
            "is_running": self.is_running,
            "mode": self.mode,
            "last_update_ts": self.last_update_ts,
            "last_update_iso": last_update_iso,
            "last_update_age_s": last_update_age_s,
            "uptime_s": max(0.0, time.monotonic() - self._uptime_start),
            **ws_snapshot,
        }

    def _run_sim_pipeline(self) -> None:
        try:
            config = self._load_sim_config()
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=config.lookback_days)
            datastore = DataStore()
            if not self._has_hf_coverage(datastore, config.symbols, start_time, end_time):
                warmup_minutes = int(os.getenv("SIM_WARMUP_MINUTES", "10"))
                recorder = BinanceHFRecorder(
                    datastore=datastore,
                    metrics=self._ws_metrics,
                )
                recorder.start(config.symbols)
                warmup_end = time.monotonic() + warmup_minutes * 60
                while time.monotonic() < warmup_end:
                    if self.stop_event.is_set():
                        recorder.stop()
                        return
                    time.sleep(1)
                recorder.stop()

            engine = ReplayEngine(
                datastore,
                config.symbols,
                start_dt=start_time,
                end_dt=end_time,
            )
            cash_per_symbol = config.initial_balance / max(len(config.symbols), 1)
            simulator = ExecutionSimulator(
                initial_cash_by_symbol={symbol: cash_per_symbol for symbol in config.symbols},
                fee_rate=config.fee_rate,
                slippage_bps=config.slippage_bps,
            )
            strategy = self._build_strategy(
                trade_notional=cash_per_symbol * 0.1,
                fee_rate=config.fee_rate,
            )

            def handle_update(_event: object, _state: object) -> None:
                self.last_update_ts = time.time()

            simulator.run_strategy(
                engine,
                strategy,
                stop_event=self.stop_event,
                update_callback=handle_update,
            )
            simulator.liquidate(engine.state_by_symbol)
            self.last_update_ts = time.time()
        finally:
            self.is_running = False

    def _run_live_engine(self) -> None:
        try:
            symbols = self._parse_symbols(os.getenv("LIVE_SYMBOLS"), ["BTCUSDT"])
            ws_url = os.getenv("LIVE_WS_URL", "wss://stream.binance.com:9443/ws")
            poll_interval = float(os.getenv("LIVE_POLL_INTERVAL", "0.5"))
            stream_cache = BinanceStreamCache(
                ws_url=ws_url,
                metrics=self._ws_metrics,
            )
            for symbol in symbols:
                stream_cache.ensure_price_stream(symbol)

            while not self.stop_event.is_set():
                updated = False
                for symbol in symbols:
                    price = stream_cache.get_price(symbol)
                    if price is None:
                        continue
                    updated = True
                    self.last_update_ts = time.time()
                if not updated:
                    time.sleep(poll_interval)
        finally:
            self.is_running = False

    def _run_testnet_engine(self) -> None:
        try:
            symbols = self._parse_symbols(os.getenv("TESTNET_SYMBOLS"), ["BTCUSDT"])
            ws_url = os.getenv("TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
            poll_interval = float(os.getenv("LIVE_POLL_INTERVAL", "0.5"))
            stream_cache = TestnetStreamCache(
                ws_url=ws_url,
                api_key=os.getenv("BINANCE_API_KEY"),
                api_secret=os.getenv("BINANCE_API_SECRET"),
                metrics=self._ws_metrics,
            )
            for symbol in symbols:
                stream_cache.ensure_price_stream(symbol)

            while not self.stop_event.is_set():
                updated = False
                for symbol in symbols:
                    price = stream_cache.get_price(symbol)
                    if price is None:
                        continue
                    updated = True
                    self.last_update_ts = time.time()
                if not updated:
                    time.sleep(poll_interval)
        finally:
            self.is_running = False

    def _run_historical_engine(self) -> None:
        try:
            datastore = DataStore()
            symbols = self._parse_symbols(os.getenv("HIST_SYMBOLS"), ["BTCUSDT"])
            ranges: list[tuple[datetime, datetime]] = []
            for symbol in symbols:
                start_dt, end_dt = datastore.available_range(symbol)
                if start_dt and end_dt:
                    ranges.append((start_dt, end_dt))
            if not ranges:
                return
            earliest_start = min(start for start, _ in ranges)
            latest_end = max(end for _, end in ranges)
            engine = ReplayEngine(
                datastore,
                symbols,
                start_dt=earliest_start,
                end_dt=latest_end,
            )
            initial_balance = float(
                os.getenv("HIST_INITIAL_BALANCE", os.getenv("SIM_INITIAL_BALANCE", "1000"))
            )
            fee_rate = float(os.getenv("HIST_FEE_RATE", os.getenv("SIM_FEE_RATE", "0.001")))
            slippage_bps = float(os.getenv("HIST_SLIPPAGE_BPS", os.getenv("SIM_SLIPPAGE_BPS", "5")))
            cash_per_symbol = initial_balance / max(len(symbols), 1)
            simulator = ExecutionSimulator(
                initial_cash_by_symbol={symbol: cash_per_symbol for symbol in symbols},
                fee_rate=fee_rate,
                slippage_bps=slippage_bps,
            )
            strategy = self._build_strategy(
                trade_notional=cash_per_symbol * 0.1,
                fee_rate=fee_rate,
            )

            def handle_update(event: object, _state: object) -> None:
                self.last_update_ts = time.time()
                if self._ws_metrics:
                    stream = getattr(event, "stream", None)
                    if stream:
                        self._ws_metrics.record_event(stream)

            simulator.run_strategy(
                engine,
                strategy,
                stop_event=self.stop_event,
                update_callback=handle_update,
            )
            simulator.liquidate(engine.state_by_symbol)
            self.last_update_ts = time.time()
        finally:
            self.is_running = False

    def _load_sim_config(self) -> SimConfig:
        symbols = self._parse_symbols(os.getenv("SIM_SYMBOLS"), ["BTCUSDT"])
        lookback_days = int(os.getenv("SIM_LOOKBACK_DAYS", str(LOOKBACK_DAYS_DEFAULT)))
        initial_balance = float(os.getenv("SIM_INITIAL_BALANCE", "1000"))
        fee_rate = float(os.getenv("SIM_FEE_RATE", "0.001"))
        slippage_bps = float(os.getenv("SIM_SLIPPAGE_BPS", "5"))
        return SimConfig(
            symbols=symbols,
            lookback_days=lookback_days,
            initial_balance=initial_balance,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
        )

    def _build_strategy(self, *, trade_notional: float, fee_rate: float) -> BaseStrategy:
        if self._use_accumulation_strategy():
            tick_size = float(os.getenv("ACCUMULATION_TICK_SIZE", "0.01"))
            min_volume_btc = float(os.getenv("ACCUMULATION_MIN_VOLUME_BTC", "5"))
            buy_side_threshold = float(os.getenv("ACCUMULATION_BUY_THRESHOLD", "0.60"))
            profit_tick = float(os.getenv("ACCUMULATION_PROFIT_TICK", str(tick_size)))
            override_notional = os.getenv("ACCUMULATION_TRADE_NOTIONAL")
            if override_notional is not None:
                trade_notional = float(override_notional)
            fee_override = os.getenv("ACCUMULATION_FEE_RATE")
            if fee_override is not None:
                fee_rate = float(fee_override)
            return AccumulationStrategy(
                trade_notional=trade_notional,
                tick_size=tick_size,
                min_volume_btc=min_volume_btc,
                buy_side_threshold=buy_side_threshold,
                profit_tick=profit_tick,
                fee_rate=fee_rate,
                observability=self._observability,
            )
        return SimReplayStrategy(trade_notional=trade_notional)

    def _use_accumulation_strategy(self) -> bool:
        flag = os.getenv("USE_ACCUMULATION_STRATEGY", "false").lower() in {"1", "true", "yes"}
        return flag or self.mode in {"LIVE", "TESTNET"}

    @staticmethod
    def _parse_symbols(value: Optional[str], default: list[str]) -> list[str]:
        if not value:
            return default
        symbols = [item.strip().upper() for item in value.replace("\n", ",").split(",")]
        return [symbol for symbol in symbols if symbol] or default

    @staticmethod
    def _has_hf_coverage(
        datastore: DataStore,
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        for symbol in symbols:
            if not datastore.has_coverage(symbol, start_time, end_time):
                return False
        return True
