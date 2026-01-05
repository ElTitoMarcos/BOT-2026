from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

from ..risk import RiskManager

@dataclass
class TradeRecord:
    symbol: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    return_pct: float
    holding_candles: int
    exit_reason: str
    fees_paid: float


@dataclass
class BacktestResult:
    total_return: float
    winrate: float
    max_drawdown: float
    profit_factor: float
    avg_trade: float
    num_trades: int
    trades: List[TradeRecord]
    report_json_path: Path
    trades_csv_path: Path
    diagnostics: Dict[str, Any]


class Backtester:
    """
    Backtester simple para señales long-only.

    Convención:
    - Entrada y salida ejecutadas al cierre de la vela.
    - TP/SL se disparan dentro de la vela usando high/low y se llenan
      al precio objetivo con slippage aplicado.
    """

    def __init__(
        self,
        initial_balance: float,
        fee_rate: float,
        slippage_bps: float,
        buffer_bps: float = 10.0,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self.initial_balance = float(initial_balance)
        self.fee_rate = float(fee_rate)
        self.slippage_bps = float(slippage_bps)
        self.buffer_bps = float(buffer_bps)
        self.risk_manager = risk_manager

    def run(
        self,
        strategy: Any,
        data_by_symbol: Dict[str, pd.DataFrame],
        *,
        data_source: str = "rest_1s_klines",
    ) -> BacktestResult:
        num_symbols = max(len(data_by_symbol), 1)
        cash_per_symbol = self.initial_balance / num_symbols
        trades: List[TradeRecord] = []
        per_symbol: List[Dict[str, Any]] = []
        events_loaded_total = 0
        entry_signals_total = 0

        for symbol, df in data_by_symbol.items():
            if df.empty:
                per_symbol.append(
                    {
                        "symbol": symbol,
                        "events": 0,
                        "entry_signals": 0,
                        "trades": 0,
                        "skip_reason": None,
                    }
                )
                continue
            df = df.reset_index(drop=True)
            signals = self._normalize_signals(strategy.entry_signal(df), df)
            entry_signals = int(signals.sum())
            symbol_trades = self._simulate_symbol(
                strategy,
                symbol,
                df,
                cash_per_symbol,
                signals=signals,
            )
            trades.extend(symbol_trades)
            events_loaded_total += len(df)
            entry_signals_total += entry_signals
            per_symbol.append(
                {
                    "symbol": symbol,
                    "events": len(df),
                    "entry_signals": entry_signals,
                    "trades": len(symbol_trades),
                    "skip_reason": None,
                }
            )

        metrics = self._calculate_metrics(trades)
        diagnostics = self._build_diagnostics(
            data_source=data_source,
            data_by_symbol=data_by_symbol,
            per_symbol=per_symbol,
            events_loaded_total=events_loaded_total,
            entry_signals_total=entry_signals_total,
            trades_executed=len(trades),
        )
        report_dir = Path("./reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_json_path = report_dir / f"backtest_{timestamp}.json"
        trades_csv_path = report_dir / f"backtest_{timestamp}_trades.csv"

        report_payload = {
            "initial_balance": self.initial_balance,
            "final_balance": self.initial_balance * (1 + metrics["total_return"]),
            "metrics": metrics,
            "diagnostics": diagnostics,
            "trades": [asdict(trade) for trade in trades],
        }
        report_json_path.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        if trades:
            trades_df = pd.DataFrame([asdict(trade) for trade in trades])
        else:
            trades_df = pd.DataFrame(
                columns=[
                    "symbol",
                    "entry_time",
                    "exit_time",
                    "entry_price",
                    "exit_price",
                    "quantity",
                    "pnl",
                    "return_pct",
                    "holding_candles",
                    "exit_reason",
                    "fees_paid",
                ]
            )
        trades_df.to_csv(trades_csv_path, index=False)

        return BacktestResult(
            total_return=metrics["total_return"],
            winrate=metrics["winrate"],
            max_drawdown=metrics["max_drawdown"],
            profit_factor=metrics["profit_factor"],
            avg_trade=metrics["avg_trade"],
            num_trades=metrics["num_trades"],
            trades=trades,
            report_json_path=report_json_path,
            trades_csv_path=trades_csv_path,
            diagnostics=diagnostics,
        )

    def _simulate_symbol(
        self,
        strategy: Any,
        symbol: str,
        df: pd.DataFrame,
        starting_cash: float,
        *,
        signals: pd.Series | None = None,
    ) -> List[TradeRecord]:
        if signals is None:
            signals = self._normalize_signals(strategy.entry_signal(df), df)
        take_profit_pct = getattr(strategy, "take_profit_pct", None)
        stop_loss_pct = getattr(strategy, "stop_loss_pct", None)
        trailing_stop_pct = getattr(strategy, "trailing_stop_pct", None)
        max_holding_candles = getattr(strategy, "max_holding_candles", None)

        if self.risk_manager is not None:
            if stop_loss_pct is None:
                stop_loss_pct = self.risk_manager.stop_loss_pct
            if take_profit_pct is None:
                take_profit_pct = self.risk_manager.take_profit_pct
            if trailing_stop_pct is None:
                trailing_stop_pct = self.risk_manager.trailing_stop_pct
            if max_holding_candles is None:
                max_holding_candles = self.risk_manager.max_holding_candles

        cash = starting_cash
        position = None
        trades: List[TradeRecord] = []
        open_positions = 0

        for idx, row in df.iterrows():
            if self.risk_manager is not None:
                equity = cash
                if position is not None:
                    equity += position["quantity"] * float(row["close"])
                self.risk_manager.update_equity(equity, self._parse_time(row["timestamp"]))
                self.risk_manager.step_cooldown()
            if position is None:
                if self.risk_manager is not None:
                    if not self.risk_manager.can_open_trade(open_positions):
                        continue
                if not signals.iloc[idx]:
                    continue
                base_price = float(row["close"])
                entry_price = self._apply_slippage(base_price, side="buy")
                cost_per_unit = entry_price * (1 + self.fee_rate)
                quantity = cash / cost_per_unit if cost_per_unit > 0 else 0
                if self.risk_manager is not None and self.risk_manager.risk_per_trade_pct:
                    risk_amount = cash * self.risk_manager.risk_per_trade_pct
                    if stop_loss_pct and stop_loss_pct > 0:
                        quantity = risk_amount / (entry_price * stop_loss_pct)
                    else:
                        quantity = risk_amount / entry_price
                    max_quantity = cash / cost_per_unit if cost_per_unit > 0 else 0
                    quantity = min(quantity, max_quantity)
                if quantity <= 0:
                    continue
                entry_fee = entry_price * quantity * self.fee_rate
                trade_cost = entry_price * quantity + entry_fee
                cash -= trade_cost
                position = {
                    "entry_index": idx,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "entry_fee": entry_fee,
                    "trade_cost": trade_cost,
                    "entry_time": self._format_time(row["timestamp"]),
                    "highest_price": entry_price,
                }
                open_positions = 1
                continue

            holding_candles = idx - position["entry_index"]
            exit_reason = None
            exit_base_price = None
            if trailing_stop_pct is not None:
                position["highest_price"] = max(position["highest_price"], float(row["high"]))
                trailing_stop_price = position["highest_price"] * (1 - trailing_stop_pct)
                if float(row["low"]) <= trailing_stop_price:
                    exit_reason = "trailing_stop"
                    exit_base_price = trailing_stop_price
            if exit_reason is None and stop_loss_pct is not None:
                stop_price = position["entry_price"] * (1 - stop_loss_pct)
                if float(row["low"]) <= stop_price:
                    exit_reason = "stop_loss"
                    exit_base_price = stop_price
            if exit_reason is None and take_profit_pct is not None:
                min_take_profit = position["entry_price"] * (
                    1 + 2 * self.fee_rate + self.buffer_bps / 10000
                )
                take_profit = position["entry_price"] * (1 + take_profit_pct)
                take_profit = max(take_profit, min_take_profit)
                if float(row["high"]) >= take_profit:
                    exit_reason = "take_profit"
                    exit_base_price = take_profit
            if exit_reason is None and max_holding_candles is not None:
                if holding_candles >= max_holding_candles:
                    exit_reason = "time_exit"
                    exit_base_price = float(row["close"])

            if exit_reason is None:
                continue

            exit_price = self._apply_slippage(exit_base_price, side="sell")
            exit_fee = exit_price * position["quantity"] * self.fee_rate
            proceeds = exit_price * position["quantity"] - exit_fee
            cash += proceeds
            pnl = proceeds - position["trade_cost"]
            return_pct = pnl / position["trade_cost"] if position["trade_cost"] > 0 else 0

            trades.append(
                TradeRecord(
                    symbol=symbol,
                    entry_time=position["entry_time"],
                    exit_time=self._format_time(row["timestamp"]),
                    entry_price=position["entry_price"],
                    exit_price=exit_price,
                    quantity=position["quantity"],
                    pnl=pnl,
                    return_pct=return_pct,
                    holding_candles=holding_candles,
                    exit_reason=exit_reason,
                    fees_paid=position["entry_fee"] + exit_fee,
                )
            )
            if self.risk_manager is not None:
                self.risk_manager.register_trade_result(pnl)
            position = None
            open_positions = 0

        if position is not None:
            last_row = df.iloc[-1]
            exit_price = self._apply_slippage(float(last_row["close"]), side="sell")
            exit_fee = exit_price * position["quantity"] * self.fee_rate
            proceeds = exit_price * position["quantity"] - exit_fee
            cash += proceeds
            pnl = proceeds - position["trade_cost"]
            return_pct = pnl / position["trade_cost"] if position["trade_cost"] > 0 else 0
            trades.append(
                TradeRecord(
                    symbol=symbol,
                    entry_time=position["entry_time"],
                    exit_time=self._format_time(last_row["timestamp"]),
                    entry_price=position["entry_price"],
                    exit_price=exit_price,
                    quantity=position["quantity"],
                    pnl=pnl,
                    return_pct=return_pct,
                    holding_candles=len(df) - 1 - position["entry_index"],
                    exit_reason="end_of_data",
                    fees_paid=position["entry_fee"] + exit_fee,
                )
            )
            if self.risk_manager is not None:
                self.risk_manager.register_trade_result(pnl)

        return trades

    def _normalize_signals(self, signals: Any, df: pd.DataFrame) -> pd.Series:
        if isinstance(signals, pd.Series):
            if len(signals) != len(df):
                raise ValueError("entry_signal debe devolver un vector del mismo tamaño")
            return signals.reset_index(drop=True).fillna(False).astype(bool)
        if isinstance(signals, Iterable) and not isinstance(signals, (str, bytes)):
            signals_list = list(signals)
            if len(signals_list) != len(df):
                raise ValueError("entry_signal debe devolver un vector del mismo tamaño")
            return pd.Series(signals_list).fillna(False).astype(bool)
        if isinstance(signals, bool):
            return pd.Series([signals] * len(df)).astype(bool)
        raise ValueError("entry_signal debe devolver un booleano o serie de booleanos")

    def _apply_slippage(self, price: float, side: str) -> float:
        slippage = self.slippage_bps / 10000
        if side == "buy":
            return price * (1 + slippage)
        if side == "sell":
            return price * (1 - slippage)
        raise ValueError("side debe ser 'buy' o 'sell'")

    def _format_time(self, value: Any) -> str:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(value / 1000).isoformat()
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        return str(value)

    def _parse_time(self, value: Any) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(value / 1000)
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return datetime.utcnow()

    def _build_diagnostics(
        self,
        *,
        data_source: str,
        data_by_symbol: Dict[str, pd.DataFrame],
        per_symbol: List[Dict[str, Any]],
        events_loaded_total: int,
        entry_signals_total: int,
        trades_executed: int,
    ) -> Dict[str, Any]:
        if trades_executed == 0:
            for item in per_symbol:
                item["skip_reason"] = self._infer_skip_reason(item)

        return {
            "universe_size": len(data_by_symbol),
            "symbols_tested": sum(1 for item in per_symbol if item["events"] > 0),
            "data_source": data_source,
            "events_loaded_total": events_loaded_total,
            "entry_signals_total": entry_signals_total,
            "trades_executed": trades_executed,
            "per_symbol": per_symbol,
        }

    @staticmethod
    def _infer_skip_reason(symbol_diag: Dict[str, Any]) -> str:
        if symbol_diag["events"] == 0:
            return "no_data"
        if symbol_diag["entry_signals"] == 0:
            return "no_signals"
        if symbol_diag["trades"] == 0:
            return "filters_blocked"
        return "unknown"

    def _calculate_metrics(self, trades: List[TradeRecord]) -> Dict[str, float]:
        num_trades = len(trades)
        if num_trades == 0:
            return {
                "total_return": 0.0,
                "winrate": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0,
                "avg_trade": 0.0,
                "num_trades": 0,
            }

        total_pnl = sum(trade.pnl for trade in trades)
        total_return = total_pnl / self.initial_balance if self.initial_balance else 0.0
        wins = [trade for trade in trades if trade.pnl > 0]
        losses = [trade for trade in trades if trade.pnl < 0]
        winrate = len(wins) / num_trades if num_trades else 0.0
        profit_sum = sum(trade.pnl for trade in wins)
        loss_sum = abs(sum(trade.pnl for trade in losses))
        if loss_sum == 0:
            profit_factor = 0.0 if profit_sum == 0 else profit_sum
        else:
            profit_factor = profit_sum / loss_sum
        avg_trade = total_pnl / num_trades

        max_drawdown = self._calculate_drawdown(trades)

        return {
            "total_return": total_return,
            "winrate": winrate,
            "max_drawdown": max_drawdown,
            "profit_factor": profit_factor,
            "avg_trade": avg_trade,
            "num_trades": num_trades,
        }

    def _calculate_drawdown(self, trades: List[TradeRecord]) -> float:
        sorted_trades = sorted(trades, key=lambda trade: trade.exit_time)
        equity = self.initial_balance
        peak = equity
        max_drawdown = 0.0
        for trade in sorted_trades:
            equity += trade.pnl
            if equity > peak:
                peak = equity
            drawdown = (equity - peak) / peak if peak else 0.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown
        return abs(max_drawdown)
