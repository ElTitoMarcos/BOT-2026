from __future__ import annotations

from typing import Any

from moneybot.backtest.simulator import SimOrder

from .base_strategy import BaseStrategy


class SimReplayStrategy(BaseStrategy):
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
