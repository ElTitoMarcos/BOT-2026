from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Iterable, List, Optional
import uuid

from moneybot.backtest.replay import MarketState


@dataclass
class SimOrder:
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None
    order_id: Optional[str] = None
    created_at: Optional[int] = None


@dataclass
class SimFill:
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    fee: float
    timestamp_us: int


@dataclass
class ExecutionReport:
    trades: List[Dict[str, float]]
    equity_curve: List[Dict[str, float]]
    balances: Dict[str, float]
    open_orders: List[SimOrder] = field(default_factory=list)


class ExecutionSimulator:
    def __init__(
        self,
        *,
        initial_cash_by_symbol: Dict[str, float],
        fee_rate: float = 0.001,
        slippage_bps: float = 0.0,
        filters_by_symbol: Optional[Dict[str, dict]] = None,
    ) -> None:
        self.cash_by_symbol = dict(initial_cash_by_symbol)
        self.positions: Dict[str, float] = {symbol: 0.0 for symbol in initial_cash_by_symbol}
        self.fee_rate = float(fee_rate)
        self.slippage = float(slippage_bps) / 10000
        self.filters_by_symbol = filters_by_symbol or {}
        self.trades: List[Dict[str, float]] = []
        self.equity_curve: List[Dict[str, float]] = []
        self.open_orders: List[SimOrder] = []

    def submit_order(self, order: SimOrder, state: MarketState) -> List[SimFill]:
        order.order_id = order.order_id or uuid.uuid4().hex
        order.created_at = order.created_at or state.last_timestamp_us
        fills: List[SimFill] = []

        if order.order_type.lower() == "market":
            fill = self._execute_order(order, state)
            if fill:
                fills.append(fill)
        elif order.order_type.lower() == "limit":
            self.open_orders.append(order)
            fill = self._maybe_fill_limit(order, state)
            if fill:
                self._remove_open_order(order.order_id)
                fills.append(fill)
        return fills

    def on_event(self, state: MarketState) -> List[SimFill]:
        fills: List[SimFill] = []
        for order in list(self.open_orders):
            if order.symbol != state.symbol:
                continue
            fill = self._maybe_fill_limit(order, state)
            if fill:
                self._remove_open_order(order.order_id)
                fills.append(fill)
        return fills

    def record_equity(self, timestamp_us: int, states: Dict[str, MarketState]) -> None:
        equity = 0.0
        for symbol, cash in self.cash_by_symbol.items():
            equity += cash
            state = states.get(symbol)
            if state is None:
                continue
            price = self._resolve_mark_price(state)
            if price is None:
                continue
            equity += self.positions.get(symbol, 0.0) * price
        self.equity_curve.append(
            {
                "timestamp": timestamp_us,
                "equity": equity,
            }
        )

    def build_report(self) -> ExecutionReport:
        balances = {symbol: self.cash_by_symbol.get(symbol, 0.0) for symbol in self.cash_by_symbol}
        return ExecutionReport(
            trades=self.trades,
            equity_curve=self.equity_curve,
            balances=balances,
            open_orders=list(self.open_orders),
        )

    def liquidate(self, states: Dict[str, MarketState]) -> None:
        for symbol, position in list(self.positions.items()):
            if position <= 0:
                continue
            state = states.get(symbol)
            if state is None:
                continue
            order = SimOrder(
                symbol=symbol,
                side="SELL",
                order_type="market",
                quantity=position,
                created_at=state.last_timestamp_us,
            )
            self.submit_order(order, state)

    def _remove_open_order(self, order_id: str) -> None:
        self.open_orders = [order for order in self.open_orders if order.order_id != order_id]

    def _maybe_fill_limit(self, order: SimOrder, state: MarketState) -> Optional[SimFill]:
        limit_price = order.price
        if limit_price is None:
            return None
        bid = state.best_bid
        ask = state.best_ask
        if order.side.upper() == "BUY":
            if ask is None or limit_price < ask:
                return None
            exec_price = min(limit_price, ask)
        else:
            if bid is None or limit_price > bid:
                return None
            exec_price = max(limit_price, bid)
        return self._execute_order(order, state, price_override=exec_price)

    def _execute_order(
        self,
        order: SimOrder,
        state: MarketState,
        *,
        price_override: Optional[float] = None,
    ) -> Optional[SimFill]:
        side = order.side.upper()
        price = price_override or self._resolve_trade_price(state, side)
        if price is None:
            return None

        price = self._apply_slippage(price, side)
        quantity = self._apply_lot_size(order.symbol, order.quantity)
        if quantity is None or quantity <= 0:
            return None

        if not self._validate_min_notional(order.symbol, price, quantity):
            return None

        notional = price * quantity
        fee = notional * self.fee_rate

        cash = self.cash_by_symbol.get(order.symbol, 0.0)
        position = self.positions.get(order.symbol, 0.0)

        if side == "BUY":
            if cash < notional + fee:
                return None
            self.cash_by_symbol[order.symbol] = cash - notional - fee
            self.positions[order.symbol] = position + quantity
        elif side == "SELL":
            if position < quantity:
                return None
            self.positions[order.symbol] = position - quantity
            self.cash_by_symbol[order.symbol] = cash + notional - fee
        else:
            return None

        timestamp_us = state.last_timestamp_us or int(datetime.utcnow().timestamp() * 1_000_000)
        fill = SimFill(
            order_id=order.order_id or uuid.uuid4().hex,
            symbol=order.symbol,
            side=side,
            order_type=order.order_type,
            price=price,
            quantity=quantity,
            fee=fee,
            timestamp_us=timestamp_us,
        )
        self._record_trade(fill)
        return fill

    def _record_trade(self, fill: SimFill) -> None:
        self.trades.append(
            {
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side,
                "order_type": fill.order_type,
                "price": fill.price,
                "quantity": fill.quantity,
                "fee": fill.fee,
                "timestamp": fill.timestamp_us,
            }
        )

    @staticmethod
    def _resolve_trade_price(state: MarketState, side: str) -> Optional[float]:
        if side == "BUY":
            return state.best_ask or state.last_trade_price
        return state.best_bid or state.last_trade_price

    @staticmethod
    def _resolve_mark_price(state: MarketState) -> Optional[float]:
        if state.best_bid and state.best_ask:
            return (state.best_bid + state.best_ask) / 2
        return state.last_trade_price

    def _apply_slippage(self, price: float, side: str) -> float:
        if self.slippage <= 0:
            return price
        if side == "BUY":
            return price * (1 + self.slippage)
        return price * (1 - self.slippage)

    def _apply_lot_size(self, symbol: str, quantity: float) -> Optional[float]:
        filters = self.filters_by_symbol.get(symbol, {})
        min_qty = filters.get("min_qty")
        max_qty = filters.get("max_qty")
        step_size = filters.get("step_size")

        qty = Decimal(str(quantity))
        if step_size:
            step = Decimal(str(step_size))
            qty = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
        if min_qty is not None and qty < Decimal(str(min_qty)):
            return None
        if max_qty is not None and qty > Decimal(str(max_qty)):
            qty = Decimal(str(max_qty))
        if qty <= 0:
            return None
        return float(qty)

    def _validate_min_notional(self, symbol: str, price: float, quantity: float) -> bool:
        filters = self.filters_by_symbol.get(symbol, {})
        min_notional = filters.get("min_notional")
        if min_notional is None:
            return True
        notional = Decimal(str(price)) * Decimal(str(quantity))
        return notional >= Decimal(str(min_notional))


def build_filters_from_exchange_info(exchange_info: dict) -> Dict[str, dict]:
    filters: Dict[str, dict] = {}
    for symbol_info in exchange_info.get("symbols", []):
        symbol = symbol_info.get("symbol")
        if not symbol:
            continue
        info: Dict[str, float] = {}
        for f in symbol_info.get("filters", []):
            filter_type = f.get("filterType")
            if filter_type == "LOT_SIZE":
                info["min_qty"] = float(f.get("minQty", 0))
                info["max_qty"] = float(f.get("maxQty", 0))
                info["step_size"] = float(f.get("stepSize", 0))
            if filter_type == "MIN_NOTIONAL":
                info["min_notional"] = float(f.get("minNotional", 0))
        filters[symbol] = info
    return filters


__all__ = [
    "ExecutionSimulator",
    "SimOrder",
    "SimFill",
    "ExecutionReport",
    "build_filters_from_exchange_info",
]
