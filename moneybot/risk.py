from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RiskManager:
    max_open_positions: int = 1
    risk_per_trade_pct: float = 0.01
    daily_drawdown_limit_pct: float = 0.05
    cooldown_candles_after_loss: int = 0
    stop_loss_pct: Optional[float] = 0.01
    take_profit_pct: Optional[float] = 0.02
    trailing_stop_pct: Optional[float] = None
    max_holding_candles: Optional[int] = None

    def __post_init__(self) -> None:
        self.kill_switch_active = False
        self.cooldown_remaining = 0
        self._daily_date = None
        self._daily_peak = None

    def can_open_trade(self, open_positions: int) -> bool:
        if self.kill_switch_active:
            return False
        if self.cooldown_remaining > 0:
            return False
        return open_positions < self.max_open_positions

    def register_trade_result(self, pnl: float) -> None:
        if pnl < 0 and self.cooldown_candles_after_loss > 0:
            self.cooldown_remaining = self.cooldown_candles_after_loss

    def step_cooldown(self) -> None:
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1

    def update_equity(self, equity: float, timestamp: Optional[datetime] = None) -> None:
        if self.daily_drawdown_limit_pct is None:
            return
        timestamp = timestamp or datetime.now(timezone.utc)
        current_date = timestamp.date()
        if self._daily_date != current_date:
            self._daily_date = current_date
            self._daily_peak = equity
            self.kill_switch_active = False
        if self._daily_peak is None:
            self._daily_peak = equity
        if equity > self._daily_peak:
            self._daily_peak = equity
        if self._daily_peak:
            drawdown = (equity - self._daily_peak) / self._daily_peak
            if drawdown <= -abs(self.daily_drawdown_limit_pct):
                self.kill_switch_active = True

    def kill_switch_triggered(self) -> bool:
        return self.kill_switch_active
