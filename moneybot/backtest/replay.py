from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import heapq
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from moneybot.datastore import DataStore


@dataclass
class ReplayEvent:
    symbol: str
    stream: str
    timestamp_us: int
    payload: dict


@dataclass
class OrderBook:
    bids: Dict[float, float] = field(default_factory=dict)
    asks: Dict[float, float] = field(default_factory=dict)

    def update_from_depth(self, payload: dict) -> None:
        for price, qty in payload.get("b", []):
            self._apply_level(self.bids, price, qty)
        for price, qty in payload.get("a", []):
            self._apply_level(self.asks, price, qty)

    @staticmethod
    def _apply_level(levels: Dict[float, float], price_raw: str, qty_raw: str) -> None:
        try:
            price = float(price_raw)
            qty = float(qty_raw)
        except (TypeError, ValueError):
            return
        if qty <= 0:
            levels.pop(price, None)
        else:
            levels[price] = qty

    def best_bid(self) -> Optional[float]:
        return max(self.bids.keys(), default=None)

    def best_ask(self) -> Optional[float]:
        return min(self.asks.keys(), default=None)


@dataclass
class MarketState:
    symbol: str
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    last_trade_price: Optional[float] = None
    last_timestamp_us: Optional[int] = None
    order_book: Optional[OrderBook] = None


class ReplayEngine:
    def __init__(
        self,
        datastore: DataStore,
        symbols: Iterable[str],
        *,
        start_dt: datetime,
        end_dt: datetime,
        streams: Optional[Iterable[str]] = None,
        use_depth_book: bool = True,
    ) -> None:
        self.datastore = datastore
        self.symbols = [symbol.upper() for symbol in symbols]
        self.start_dt = start_dt
        self.end_dt = end_dt
        self.streams = list(streams or ["aggTrade", "depth", "bookTicker"])
        self.use_depth_book = use_depth_book
        self.state_by_symbol: Dict[str, MarketState] = {
            symbol: MarketState(symbol=symbol, order_book=OrderBook() if use_depth_book else None)
            for symbol in self.symbols
        }
        self._start_ts_us = int(start_dt.timestamp() * 1_000_000)
        self._end_ts_us = int(end_dt.timestamp() * 1_000_000)

    def iter_events(self) -> Iterator[ReplayEvent]:
        heap: List[Tuple[int, int, ReplayEvent, Iterator[ReplayEvent]]] = []
        counter = 0
        for symbol in self.symbols:
            for stream in self.streams:
                iterator = self._iter_stream_events(symbol, stream)
                try:
                    first = next(iterator)
                except StopIteration:
                    continue
                heapq.heappush(heap, (first.timestamp_us, counter, first, iterator))
                counter += 1

        while heap:
            _ts, _counter, event, iterator = heapq.heappop(heap)
            yield event
            try:
                next_event = next(iterator)
            except StopIteration:
                continue
            heapq.heappush(
                heap,
                (next_event.timestamp_us, counter, next_event, iterator),
            )
            counter += 1

    def update_state(self, event: ReplayEvent) -> MarketState:
        state = self.state_by_symbol[event.symbol]
        state.last_timestamp_us = event.timestamp_us

        if event.stream == "aggTrade":
            price_raw = event.payload.get("p")
            try:
                state.last_trade_price = float(price_raw)
            except (TypeError, ValueError):
                pass
        elif event.stream == "bookTicker":
            bid_raw = event.payload.get("b")
            ask_raw = event.payload.get("a")
            try:
                state.best_bid = float(bid_raw)
            except (TypeError, ValueError):
                pass
            try:
                state.best_ask = float(ask_raw)
            except (TypeError, ValueError):
                pass
        elif event.stream == "depth":
            if state.order_book is not None:
                state.order_book.update_from_depth(event.payload)
                state.best_bid = state.order_book.best_bid() or state.best_bid
                state.best_ask = state.order_book.best_ask() or state.best_ask

        if state.best_bid is None or state.best_ask is None:
            if state.order_book is not None:
                state.best_bid = state.best_bid or state.order_book.best_bid()
                state.best_ask = state.best_ask or state.order_book.best_ask()

        return state

    def _iter_stream_events(self, symbol: str, stream: str) -> Iterator[ReplayEvent]:
        start_ts_ms = int(self.start_dt.timestamp() * 1000)
        end_ts_ms = int(self.end_dt.timestamp() * 1000)
        for event in self.datastore.iter_events(symbol, stream, start_ts_ms, end_ts_ms):
            ts_us = self._event_timestamp_us(event)
            if ts_us < self._start_ts_us or ts_us > self._end_ts_us:
                continue
            yield ReplayEvent(
                symbol=symbol,
                stream=stream,
                timestamp_us=ts_us,
                payload=event,
            )

    @staticmethod
    def _event_timestamp_us(event: dict) -> int:
        raw = event.get("T") or event.get("E") or event.get("eventTime") or 0
        try:
            ts = int(raw)
        except (TypeError, ValueError):
            return 0
        if ts > 1e14:
            return ts
        if ts > 1e11:
            return ts * 1000
        return ts * 1_000_000


__all__ = ["ReplayEngine", "ReplayEvent", "MarketState", "OrderBook"]
