from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

from .backtest import Backtester
from .data_provider import BinanceKlinesProvider
from .strategy import Strategy


@dataclass
class TrendStrategy:
    trend_engine: Strategy = field(default_factory=Strategy)
    take_profit_pct: float = 0.03
    stop_loss_pct: float = 0.01
    max_holding_candles: int = 24

    def entry_signal(self, df: pd.DataFrame) -> pd.Series:
        tendencias = self.trend_engine.calcular_tendencias(df)
        return (tendencias == "ALCISTA").fillna(False)


def main() -> None:
    provider = BinanceKlinesProvider()
    symbol = "BTCUSDT"
    interval = "1h"
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=30)

    df = provider.get_ohlcv(symbol, interval, start_time, end_time)
    data_by_symbol = {symbol: df}

    strategy = TrendStrategy()
    backtester = Backtester(initial_balance=1000.0, fee_rate=0.001, slippage_bps=5)
    result = backtester.run(strategy, data_by_symbol)

    print("Resumen del backtest")
    print(f"Trades: {result.num_trades}")
    print(f"Total return: {result.total_return:.2%}")
    print(f"Winrate: {result.winrate:.2%}")
    print(f"Max drawdown: {result.max_drawdown:.2%}")
    print(f"Profit factor: {result.profit_factor:.2f}")
    print(f"Avg trade: {result.avg_trade:.2f}")
    print(f"Reporte JSON: {result.report_json_path}")
    print(f"Trades CSV: {result.trades_csv_path}")


if __name__ == "__main__":
    main()
