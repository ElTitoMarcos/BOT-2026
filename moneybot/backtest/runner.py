from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import uuid
import zipfile
from typing import Any, Dict, List

import pandas as pd

from moneybot.data_provider import BinanceKlinesProvider


@dataclass
class BacktestJob:
    job_id: str
    state: str
    progress: int
    message: str
    report_dir: Path
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


class BacktestJobManager:
    def __init__(self) -> None:
        self.jobs: Dict[str, BacktestJob] = {}
        self._lock = threading.Lock()

    def run_job(self, payload: Dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex
        report_dir = Path("./reports") / job_id
        job = BacktestJob(
            job_id=job_id,
            state="queued",
            progress=0,
            message="Encolado",
            report_dir=report_dir,
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self.jobs[job_id] = job
        thread = threading.Thread(target=self._execute_job, args=(job_id, payload), daemon=True)
        thread.start()
        return job_id

    def get_status(self, job_id: str) -> BacktestJob | None:
        with self._lock:
            return self.jobs.get(job_id)

    def read_results(self, job_id: str) -> Dict[str, Any]:
        job = self.get_status(job_id)
        if job is None:
            raise FileNotFoundError("Job no encontrado")
        summary_path = job.report_dir / "summary.json"
        equity_path = job.report_dir / "equity.csv"
        trades_path = job.report_dir / "trades.csv"
        if not summary_path.exists():
            raise FileNotFoundError("Resumen no disponible")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        equity_series = []
        if equity_path.exists():
            equity_df = pd.read_csv(equity_path)
            equity_series = equity_df.to_dict(orient="records")
        trades = []
        if trades_path.exists():
            trades_df = pd.read_csv(trades_path)
            trades = trades_df.to_dict(orient="records")
        return {
            "summary": summary,
            "equity_series": equity_series,
            "trades": trades,
        }

    def build_zip(self, job_id: str) -> Path:
        job = self.get_status(job_id)
        if job is None:
            raise FileNotFoundError("Job no encontrado")
        if not job.report_dir.exists():
            raise FileNotFoundError("Reporte no encontrado")
        zip_path = job.report_dir / "report.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            for filename in ["summary.json", "equity.csv", "trades.csv"]:
                file_path = job.report_dir / filename
                if file_path.exists():
                    zipf.write(file_path, arcname=filename)
        return zip_path

    def _execute_job(self, job_id: str, payload: Dict[str, Any]) -> None:
        try:
            self._update_job(job_id, state="running", progress=5, message="Preparando")
            symbols = payload.get("symbols", [])
            if not symbols:
                raise ValueError("Debe incluir al menos un símbolo")
            interval = payload.get("interval", "1h")
            start_date = payload.get("start_date")
            end_date = payload.get("end_date")
            if not start_date or not end_date:
                raise ValueError("start_date y end_date son requeridos")
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
            if start_dt > end_dt:
                raise ValueError("start_date debe ser menor o igual que end_date")
            initial_balance = float(payload.get("initial_balance", 1000.0))
            fee_rate = float(payload.get("fee_rate", 0.001))
            slippage_bps = float(payload.get("slippage_bps", 0.0))
            self._update_job(job_id, progress=15, message="Descargando datos")
            provider = BinanceKlinesProvider()
            data_by_symbol: Dict[str, pd.DataFrame] = {}
            for symbol in symbols:
                data_by_symbol[symbol] = provider.get_ohlcv(
                    symbol,
                    interval,
                    start_dt,
                    end_dt,
                )
            self._update_job(job_id, progress=45, message="Ejecutando backtest")
            result = _run_simple_backtest(
                data_by_symbol,
                initial_balance=initial_balance,
                fee_rate=fee_rate,
                slippage_bps=slippage_bps,
            )
            self._update_job(job_id, progress=80, message="Guardando reporte")
            report_dir = Path("./reports") / job_id
            report_dir.mkdir(parents=True, exist_ok=True)
            _save_report(report_dir, result)
            self._update_job(job_id, state="completed", progress=100, message="Completado")
        except Exception as exc:  # noqa: BLE001 - report status on job
            self._update_job(
                job_id,
                state="failed",
                progress=100,
                message=f"Error: {exc}",
                error=str(exc),
            )

    def _update_job(
        self,
        job_id: str,
        *,
        state: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            if state:
                job.state = state
            if progress is not None:
                job.progress = int(progress)
            if message:
                job.message = message
            if error:
                job.error = error
            if state in {"completed", "failed"}:
                job.finished_at = datetime.now(timezone.utc)


def _run_simple_backtest(
    data_by_symbol: Dict[str, pd.DataFrame],
    *,
    initial_balance: float,
    fee_rate: float,
    slippage_bps: float,
) -> Dict[str, Any]:
    slippage = slippage_bps / 10000
    num_symbols = max(len(data_by_symbol), 1)
    cash_per_symbol = initial_balance / num_symbols
    all_trades: List[Dict[str, Any]] = []
    equity_frames: List[pd.DataFrame] = []
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
        df = df.sort_values("timestamp").reset_index(drop=True)
        cash = cash_per_symbol
        position = None
        equity_rows: List[Dict[str, Any]] = []
        symbol_entry_signals = int((df["close"] > df["open"]).sum())
        symbol_trades = 0
        events_loaded_total += len(df)
        entry_signals_total += symbol_entry_signals

        for idx, row in df.iterrows():
            timestamp = row["timestamp"]
            close_price = float(row["close"])
            open_price = float(row["open"])

            if position is None:
                if close_price <= open_price:
                    equity_rows.append({"timestamp": timestamp, "equity": cash})
                    continue
                entry_price = close_price * (1 + slippage)
                quantity = cash / (entry_price * (1 + fee_rate)) if entry_price > 0 else 0
                entry_fee = entry_price * quantity * fee_rate
                if quantity <= 0:
                    equity_rows.append({"timestamp": timestamp, "equity": cash})
                    continue
                trade_cost = entry_price * quantity + entry_fee
                cash -= trade_cost
                position = {
                    "entry_index": idx,
                    "entry_price": entry_price,
                    "entry_time": _format_time(timestamp),
                    "quantity": quantity,
                    "entry_fee": entry_fee,
                    "trade_cost": trade_cost,
                }
                equity_rows.append({"timestamp": timestamp, "equity": cash + quantity * close_price})
                continue

            exit_price = close_price * (1 - slippage)
            exit_fee = exit_price * position["quantity"] * fee_rate
            proceeds = exit_price * position["quantity"] - exit_fee
            cash += proceeds
            pnl = proceeds - position["trade_cost"]
            return_pct = pnl / position["trade_cost"] if position["trade_cost"] else 0

            all_trades.append(
                {
                    "symbol": symbol,
                    "entry_time": position["entry_time"],
                    "exit_time": _format_time(timestamp),
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "quantity": position["quantity"],
                    "pnl": pnl,
                    "return_pct": return_pct,
                    "holding_candles": idx - position["entry_index"],
                    "exit_reason": "next_candle",
                    "fees_paid": position["entry_fee"] + exit_fee,
                }
            )
            symbol_trades += 1
            position = None
            equity_rows.append({"timestamp": timestamp, "equity": cash})

        if position is not None:
            last_row = df.iloc[-1]
            exit_price = float(last_row["close"]) * (1 - slippage)
            exit_fee = exit_price * position["quantity"] * fee_rate
            proceeds = exit_price * position["quantity"] - exit_fee
            cash += proceeds
            pnl = proceeds - position["trade_cost"]
            return_pct = pnl / position["trade_cost"] if position["trade_cost"] else 0
            all_trades.append(
                {
                    "symbol": symbol,
                    "entry_time": position["entry_time"],
                    "exit_time": _format_time(last_row["timestamp"]),
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "quantity": position["quantity"],
                    "pnl": pnl,
                    "return_pct": return_pct,
                    "holding_candles": len(df) - 1 - position["entry_index"],
                    "exit_reason": "end_of_data",
                    "fees_paid": position["entry_fee"] + exit_fee,
                }
            )
            symbol_trades += 1
            equity_rows.append({"timestamp": last_row["timestamp"], "equity": cash})

        equity_frames.append(pd.DataFrame(equity_rows))
        per_symbol.append(
            {
                "symbol": symbol,
                "events": len(df),
                "entry_signals": symbol_entry_signals,
                "trades": symbol_trades,
                "skip_reason": None,
            }
        )

    if equity_frames:
        equity_df = equity_frames[0]
        for extra in equity_frames[1:]:
            equity_df = equity_df.merge(extra, on="timestamp", how="outer", suffixes=("", "_extra"))
            equity_cols = [col for col in equity_df.columns if col.startswith("equity")]
            equity_df["equity"] = equity_df[equity_cols].sum(axis=1)
            equity_df = equity_df[["timestamp", "equity"]]
        equity_df = equity_df.sort_values("timestamp").reset_index(drop=True)
    else:
        equity_df = pd.DataFrame(columns=["timestamp", "equity"])

    summary = _calculate_summary(all_trades, equity_df, initial_balance)
    diagnostics = _build_diagnostics(
        data_by_symbol=data_by_symbol,
        per_symbol=per_symbol,
        events_loaded_total=events_loaded_total,
        entry_signals_total=entry_signals_total,
        trades_executed=len(all_trades),
    )
    summary["diagnostics"] = diagnostics
    return {
        "summary": summary,
        "equity": equity_df,
        "trades": all_trades,
    }


def _calculate_summary(
    trades: List[Dict[str, Any]],
    equity_df: pd.DataFrame,
    initial_balance: float,
) -> Dict[str, Any]:
    total_pnl = sum(trade["pnl"] for trade in trades)
    total_return = total_pnl / initial_balance if initial_balance else 0
    num_trades = len(trades)
    wins = [trade for trade in trades if trade["pnl"] > 0]
    losses = [trade for trade in trades if trade["pnl"] < 0]
    winrate = len(wins) / num_trades if num_trades else 0
    profit_sum = sum(trade["pnl"] for trade in wins)
    loss_sum = abs(sum(trade["pnl"] for trade in losses))
    profit_factor = profit_sum / loss_sum if loss_sum else (profit_sum if profit_sum else 0)
    max_drawdown = 0.0
    if not equity_df.empty:
        equity = equity_df["equity"].fillna(method="ffill").fillna(initial_balance)
        peak = equity.iloc[0] if not equity.empty else initial_balance
        for value in equity:
            if value > peak:
                peak = value
            drawdown = (value - peak) / peak if peak else 0
            if drawdown < max_drawdown:
                max_drawdown = drawdown
        max_drawdown = abs(max_drawdown)

    return {
        "initial_balance": initial_balance,
        "final_balance": initial_balance + total_pnl,
        "total_return": total_return,
        "num_trades": num_trades,
        "winrate": winrate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
    }


def _build_diagnostics(
    *,
    data_by_symbol: Dict[str, pd.DataFrame],
    per_symbol: List[Dict[str, Any]],
    events_loaded_total: int,
    entry_signals_total: int,
    trades_executed: int,
) -> Dict[str, Any]:
    if trades_executed == 0:
        for item in per_symbol:
            item["skip_reason"] = _infer_skip_reason(item)

    return {
        "universe_size": len(data_by_symbol),
        "symbols_tested": sum(1 for item in per_symbol if item["events"] > 0),
        "data_source": "rest_1s_klines",
        "events_loaded_total": events_loaded_total,
        "entry_signals_total": entry_signals_total,
        "trades_executed": trades_executed,
        "per_symbol": per_symbol,
    }


def _infer_skip_reason(symbol_diag: Dict[str, Any]) -> str:
    if symbol_diag["events"] == 0:
        return "no_data"
    if symbol_diag["entry_signals"] == 0:
        return "no_signals"
    if symbol_diag["trades"] == 0:
        return "filters_blocked"
    return "unknown"


def _save_report(report_dir: Path, result: Dict[str, Any]) -> None:
    summary_path = report_dir / "summary.json"
    equity_path = report_dir / "equity.csv"
    trades_path = report_dir / "trades.csv"

    summary_path.write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result["equity"].to_csv(equity_path, index=False)
    trades_df = pd.DataFrame(result["trades"])
    trades_df.to_csv(trades_path, index=False)


def _format_time(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value / 1000).isoformat()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)
