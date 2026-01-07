from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional

from moneybot.backtest.simulator import SimOrder
from moneybot.observability import ObservabilityStore

from .base_strategy import BaseStrategy


@dataclass
class SymbolAccumulationState:
    last_event_ts_us: Optional[int] = None
    trades: Deque[tuple[int, float, bool]] = field(default_factory=deque)
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    pending_order_id: Optional[str] = None
    pending_side: Optional[str] = None
    position_qty: float = 0.0
    entry_price: Optional[float] = None
    entry_fee: float = 0.0
    bid_qty: Optional[float] = None
    ask_qty: Optional[float] = None
    last_price: Optional[float] = None
    queued_orders: list[SimOrder] = field(default_factory=list)


class AccumulationStrategy(BaseStrategy):
    def __init__(
        self,
        *,
        trade_notional: float,
        tick_size: float,
        min_volume_btc: float,
        buy_side_threshold: float,
        profit_tick: float,
        fee_rate: float = 0.0,
        observability: Optional[ObservabilityStore] = None,
    ) -> None:
        if buy_side_threshold < 0.60:
            raise ValueError("buy_side_threshold debe ser >= 0.60")
        self.trade_notional = trade_notional
        self.tick_size = tick_size
        self.min_volume_btc = min_volume_btc
        self.buy_side_threshold = buy_side_threshold
        self.profit_tick = profit_tick
        self.fee_rate = fee_rate
        self.observability = observability or ObservabilityStore()
        self._state_by_symbol: dict[str, SymbolAccumulationState] = {}

    def on_event(self, event: Any, state: Any) -> list[SimOrder]:
        symbol = getattr(event, "symbol", None) or getattr(state, "symbol", None)
        if not symbol:
            return []
        symbol_state = self._state_by_symbol.setdefault(symbol, SymbolAccumulationState())
        orders: list[SimOrder] = []
        if symbol_state.queued_orders:
            orders.extend(symbol_state.queued_orders)
            symbol_state.queued_orders = []

        stream = getattr(event, "stream", None)
        payload = getattr(event, "payload", None) or {}
        timestamp_us = getattr(event, "timestamp_us", None)
        if timestamp_us is None:
            timestamp_us = int(time.time() * 1_000_000)
        symbol_state.last_event_ts_us = timestamp_us

        if stream == "aggTrade":
            self._update_trade_volume(symbol_state, payload, timestamp_us)
        if stream in {"depth", "bookTicker"}:
            self._update_book_snapshot(symbol_state, stream, payload, state)

        current_price = state.best_ask or state.last_trade_price or state.best_bid
        previous_price = symbol_state.last_price
        if current_price is not None:
            symbol_state.last_price = current_price

        total_volume = symbol_state.buy_volume + symbol_state.sell_volume
        buy_ratio = self._buy_side_ratio(symbol_state)
        has_resistance = self._has_strong_resistance(symbol_state)

        if symbol_state.pending_order_id and symbol_state.pending_side == "BUY":
            cancel_reason = self._cancel_reason(
                current_price,
                buy_ratio,
                total_volume,
                has_resistance,
                previous_price,
            )
            if cancel_reason:
                orders.append(
                    SimOrder(
                        symbol=symbol,
                        side="BUY",
                        order_type="cancel",
                        quantity=0.0,
                        order_id=symbol_state.pending_order_id,
                    )
                )
                logging.info(
                    "Cancelando BUY pendiente por %s en %s.",
                    cancel_reason,
                    symbol,
                )
                symbol_state.pending_order_id = None
                symbol_state.pending_side = None

        if symbol_state.position_qty <= 0 and symbol_state.pending_order_id is None:
            if self._entry_conditions_met(symbol_state, buy_ratio, total_volume, has_resistance, current_price):
                order_id = uuid.uuid4().hex
                orders.append(
                    SimOrder(
                        symbol=symbol,
                        side="BUY",
                        order_type="limit",
                        quantity=self.trade_notional / current_price,
                        price=current_price,
                        order_id=order_id,
                    )
                )
                symbol_state.pending_order_id = order_id
                symbol_state.pending_side = "BUY"
                logging.info(
                    "Entrada BUY en %s a %.8f (ratio %.2f, vol %.2f).",
                    symbol,
                    current_price,
                    buy_ratio or 0.0,
                    total_volume,
                )

        if symbol_state.position_qty > 0 and symbol_state.pending_order_id is None:
            target_price = symbol_state.entry_price
            if target_price is not None:
                target_price += max(self.tick_size, self.profit_tick)
                order_id = uuid.uuid4().hex
                orders.append(
                    SimOrder(
                        symbol=symbol,
                        side="SELL",
                        order_type="limit",
                        quantity=symbol_state.position_qty,
                        price=target_price,
                        order_id=order_id,
                    )
                )
                symbol_state.pending_order_id = order_id
                symbol_state.pending_side = "SELL"
                logging.info(
                    "Salida objetivo en %s a %.8f.",
                    symbol,
                    target_price,
                )

        return orders

    def on_fill(self, fill: Any) -> None:
        symbol = getattr(fill, "symbol", None)
        if not symbol:
            return
        symbol_state = self._state_by_symbol.setdefault(symbol, SymbolAccumulationState())
        side = fill.side.upper()
        fill_fee = getattr(fill, "fee", None)
        if fill_fee is None:
            fill_fee = fill.price * fill.quantity * self.fee_rate
        if side == "BUY":
            symbol_state.position_qty += fill.quantity
            symbol_state.entry_price = fill.price
            symbol_state.entry_fee = fill_fee
            symbol_state.pending_order_id = None
            symbol_state.pending_side = None
            logging.info(
                "BUY ejecutado en %s a %.8f por %.6f.",
                symbol,
                fill.price,
                fill.quantity,
            )
        elif side == "SELL":
            prior_position = symbol_state.position_qty
            symbol_state.position_qty = max(0.0, symbol_state.position_qty - fill.quantity)
            pnl_delta = 0.0
            if symbol_state.entry_price is not None and prior_position > 0:
                entry_fee = symbol_state.entry_fee
                pnl_delta = (fill.price - symbol_state.entry_price) * fill.quantity
                pnl_delta -= entry_fee + fill_fee
                self.observability.record_result(pnl_delta)
            symbol_state.pending_order_id = None
            symbol_state.pending_side = None
            if symbol_state.position_qty <= 0:
                symbol_state.entry_price = None
                symbol_state.entry_fee = 0.0
            logging.info(
                "SELL ejecutado en %s a %.8f por %.6f. PnL %.4f.",
                symbol,
                fill.price,
                fill.quantity,
                pnl_delta,
            )

    def _update_trade_volume(self, symbol_state: SymbolAccumulationState, payload: dict, timestamp_us: int) -> None:
        qty = self._to_float(payload.get("q")) or 0.0
        is_buy = not bool(payload.get("m"))
        symbol_state.trades.append((timestamp_us, qty, is_buy))
        if is_buy:
            symbol_state.buy_volume += qty
        else:
            symbol_state.sell_volume += qty
        self._prune_trades(symbol_state, timestamp_us)

    def _prune_trades(self, symbol_state: SymbolAccumulationState, now_us: int) -> None:
        cutoff = now_us - 60 * 1_000_000
        while symbol_state.trades and symbol_state.trades[0][0] < cutoff:
            _ts, qty, is_buy = symbol_state.trades.popleft()
            if is_buy:
                symbol_state.buy_volume = max(0.0, symbol_state.buy_volume - qty)
            else:
                symbol_state.sell_volume = max(0.0, symbol_state.sell_volume - qty)

    def _update_book_snapshot(
        self,
        symbol_state: SymbolAccumulationState,
        stream: str,
        payload: dict,
        state: Any,
    ) -> None:
        if stream == "bookTicker":
            bid_qty = self._to_float(payload.get("B"))
            ask_qty = self._to_float(payload.get("A"))
            if bid_qty is not None:
                symbol_state.bid_qty = bid_qty
            if ask_qty is not None:
                symbol_state.ask_qty = ask_qty
        elif stream == "depth" and getattr(state, "order_book", None) is not None:
            best_bid = getattr(state, "best_bid", None)
            best_ask = getattr(state, "best_ask", None)
            order_book = state.order_book
            if best_bid is not None:
                symbol_state.bid_qty = order_book.bids.get(best_bid, symbol_state.bid_qty)
            if best_ask is not None:
                symbol_state.ask_qty = order_book.asks.get(best_ask, symbol_state.ask_qty)

    def _buy_side_ratio(self, symbol_state: SymbolAccumulationState) -> Optional[float]:
        if symbol_state.bid_qty is None or symbol_state.ask_qty is None:
            return None
        total = symbol_state.bid_qty + symbol_state.ask_qty
        if total <= 0:
            return None
        return symbol_state.bid_qty / total

    def _has_strong_resistance(self, symbol_state: SymbolAccumulationState) -> bool:
        if symbol_state.bid_qty is None or symbol_state.ask_qty is None:
            return False
        if symbol_state.bid_qty <= 0:
            return True
        return symbol_state.ask_qty >= symbol_state.bid_qty * 2

    def _entry_conditions_met(
        self,
        symbol_state: SymbolAccumulationState,
        buy_ratio: Optional[float],
        total_volume: float,
        has_resistance: bool,
        current_price: Optional[float],
    ) -> bool:
        if current_price is None:
            return False
        if total_volume < self.min_volume_btc:
            return False
        if buy_ratio is None or buy_ratio < self.buy_side_threshold:
            return False
        if has_resistance:
            return False
        return True

    def _cancel_reason(
        self,
        current_price: Optional[float],
        buy_ratio: Optional[float],
        total_volume: float,
        has_resistance: bool,
        previous_price: Optional[float],
    ) -> Optional[str]:
        if total_volume < self.min_volume_btc:
            return "volumen bajo"
        if buy_ratio is not None and buy_ratio < self.buy_side_threshold:
            return "acumulación insuficiente"
        if has_resistance:
            return "resistencia fuerte"
        if current_price is not None and previous_price is not None:
            if current_price < previous_price - self.tick_size:
                return "caída de precio"
        return None

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
