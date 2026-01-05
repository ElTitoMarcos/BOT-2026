from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from moneybot.backtest import Backtester
from moneybot.backtest.replay import replay_from_datastore
from moneybot.config import HF_INTERVAL, LOOKBACK_DAYS_DEFAULT
from moneybot.data_provider import BinanceKlinesProvider
from moneybot.datastore import DataStore
from moneybot.market.recorder import BinanceHFRecorder
from moneybot.market_streams import BinanceStreamCache
from moneybot.risk import RiskManager
from moneybot.strategy import Strategy


@dataclass
class SimConfig:
    symbols: list[str]
    interval: str
    lookback_days: int
    initial_balance: float
    fee_rate: float
    slippage_bps: float


class SimTrendStrategy:
    def __init__(self) -> None:
        self.trend_engine = Strategy()
        self.take_profit_pct = 0.03
        self.stop_loss_pct = 0.01
        self.max_holding_candles = 24

    def entry_signal(self, df):
        tendencias = self.trend_engine.calcular_tendencias(df)
        return (tendencias == "ALCISTA").fillna(False)


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
            data_by_symbol = {}
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

            data_by_symbol = replay_from_datastore(
                datastore,
                config.symbols,
                start_dt=start_time,
                end_dt=end_time,
                interval=config.interval,
            )
            has_replay_data = (
                any(not df.empty for df in data_by_symbol.values())
                if data_by_symbol
                else False
            )
            if not has_replay_data:
                provider = BinanceKlinesProvider()
                for symbol in config.symbols:
                    if self.stop_event.is_set():
                        return
                    data_by_symbol[symbol] = provider.get_ohlcv(
                        symbol, config.interval, start_time, end_time
                    )
                    self.last_update_ts = time.time()
            self.last_update_ts = time.time()

            strategy = SimTrendStrategy()
            risk_manager = RiskManager(
                max_open_positions=1,
                risk_per_trade_pct=0.02,
                daily_drawdown_limit_pct=0.05,
                cooldown_candles_after_loss=3,
                stop_loss_pct=strategy.stop_loss_pct,
                take_profit_pct=strategy.take_profit_pct,
                trailing_stop_pct=None,
                max_holding_candles=strategy.max_holding_candles,
            )
            backtester = Backtester(
                initial_balance=config.initial_balance,
                fee_rate=config.fee_rate,
                slippage_bps=config.slippage_bps,
                buffer_bps=10,
                risk_manager=risk_manager,
            )
            backtester.run(strategy, data_by_symbol)
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
        interval = os.getenv("SIM_INTERVAL", HF_INTERVAL)
        lookback_days = int(os.getenv("SIM_LOOKBACK_DAYS", str(LOOKBACK_DAYS_DEFAULT)))
        initial_balance = float(os.getenv("SIM_INITIAL_BALANCE", "1000"))
        fee_rate = float(os.getenv("SIM_FEE_RATE", "0.001"))
        slippage_bps = float(os.getenv("SIM_SLIPPAGE_BPS", "5"))
        return SimConfig(
            symbols=symbols,
            interval=interval,
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
