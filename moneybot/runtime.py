from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from moneybot.backtest.replay import ReplayEngine
from moneybot.backtest.simulator import ExecutionSimulator, SimOrder
from moneybot.config import LOOKBACK_DAYS_DEFAULT
from moneybot.datastore import DataStore
from moneybot.market.recorder import BinanceHFRecorder
from moneybot.market_streams import BinanceStreamCache


@dataclass
class SimConfig:
    symbols: list[str]
    lookback_days: int
    initial_balance: float
    fee_rate: float
    slippage_bps: float


class SimReplayStrategy:
    def __init__(self, *, trade_notional: float, entry_bps: float = 5.0, exit_bps: float = 5.0) -> None:
        self.trade_notional = trade_notional
        self.entry_bps = entry_bps
        self.exit_bps = exit_bps
        self.last_price: dict[str, float] = {}
        self.positions: dict[str, float] = {}

    def on_event(self, event: Any, state: Any) -> list[SimOrder]:
        if event.stream != "aggTrade":
            return []
        price = state.last_trade_price
        if price is None:
            return []
        last = self.last_price.get(event.symbol)
        self.last_price[event.symbol] = price
        if last is None:
            return []
        position = self.positions.get(event.symbol, 0.0)
        if position <= 0 and price > last * (1 + self.entry_bps / 10000):
            qty = self.trade_notional / price
            return [
                SimOrder(
                    symbol=event.symbol,
                    side="BUY",
                    order_type="market",
                    quantity=qty,
                )
            ]
        if position > 0 and price < last * (1 - self.exit_bps / 10000):
            return [
                SimOrder(
                    symbol=event.symbol,
                    side="SELL",
                    order_type="market",
                    quantity=position,
                )
            ]
        return []

    def on_fill(self, fill: Any) -> None:
        position = self.positions.get(fill.symbol, 0.0)
        if fill.side.upper() == "BUY":
            self.positions[fill.symbol] = position + fill.quantity
        else:
            self.positions[fill.symbol] = max(0.0, position - fill.quantity)


class BotRuntime:
    def __init__(self, mode: str = "SIM") -> None:
        self.is_running = False
        self.mode = mode
        self.last_update_ts: Optional[float] = None
        self.stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self.stop_event.clear()
            self.is_running = True
            self.last_update_ts = time.time()
            target = self._run_sim_pipeline if self.mode == "SIM" else self._run_live_engine
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
        self.mode = mode

    def status(self) -> dict:
        return {
            "is_running": self.is_running,
            "mode": self.mode,
            "last_update_ts": self.last_update_ts,
        }

    def _run_sim_pipeline(self) -> None:
        try:
            config = self._load_sim_config()
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=config.lookback_days)
            datastore = DataStore()
            if not self._has_hf_coverage(datastore, config.symbols, start_time, end_time):
                warmup_minutes = int(os.getenv("SIM_WARMUP_MINUTES", "10"))
                recorder = BinanceHFRecorder(datastore=datastore)
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
            strategy = SimReplayStrategy(trade_notional=cash_per_symbol * 0.1)

            for event in engine.iter_events():
                if self.stop_event.is_set():
                    return
                state = engine.update_state(event)
                fills = []
                for order in strategy.on_event(event, state):
                    fills.extend(simulator.submit_order(order, state))
                fills.extend(simulator.on_event(state))
                for fill in fills:
                    strategy.on_fill(fill)
                simulator.record_equity(event.timestamp_us, engine.state_by_symbol)
                self.last_update_ts = time.time()
            simulator.liquidate(engine.state_by_symbol)
            self.last_update_ts = time.time()
        finally:
            self.is_running = False

    def _run_live_engine(self) -> None:
        try:
            symbols = self._parse_symbols(os.getenv("LIVE_SYMBOLS"), ["BTCUSDT"])
            ws_url = os.getenv("LIVE_WS_URL", "wss://stream.binance.com:9443/ws")
            poll_interval = float(os.getenv("LIVE_POLL_INTERVAL", "0.5"))
            stream_cache = BinanceStreamCache(ws_url=ws_url)
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
