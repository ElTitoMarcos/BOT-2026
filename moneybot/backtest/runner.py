from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import json
import threading
import time
import uuid
import zipfile
from typing import Any, Dict, Iterable, List

import pandas as pd

from moneybot.backtest.replay import ReplayEngine
from moneybot.backtest.simulator import ExecutionSimulator, build_filters_from_exchange_info
from moneybot.config import LOOKBACK_DAYS_DEFAULT
from moneybot.datastore import DataStore
from moneybot.market.recorder import BinanceHFRecorder
from moneybot.rate_limiter import BinanceRestClient
from moneybot.strategy.simple_strategy import SimReplayStrategy
from moneybot.universe import build_universe


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
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        summary = summary_payload.get("summary", summary_payload)
        diagnostics = summary_payload.get("diagnostics", {})
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
            "diagnostics": diagnostics,
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
            symbols = payload.get("symbols") or []
            start_date = payload.get("start_date")
            end_date = payload.get("end_date")

            if not symbols:
                symbols = build_universe()

            start_dt, end_dt = _resolve_date_range(start_date, end_date)
            if start_dt > end_dt:
                raise ValueError("start_date debe ser menor o igual que end_date")

            initial_balance = float(payload.get("initial_balance", 1000.0))
            fee_rate = float(payload.get("fee_rate", 0.001))
            slippage_bps = float(payload.get("slippage_bps", 0.0))

            self._update_job(job_id, progress=15, message="Verificando datos")
            datastore = DataStore()
            _ensure_datastore_coverage(datastore, symbols, start_dt, end_dt)

            self._update_job(job_id, progress=35, message="Cargando filtros")
            filters_by_symbol = _load_exchange_filters()

            self._update_job(job_id, progress=55, message="Ejecutando backtest")
            result = _run_replay_backtest(
                datastore,
                symbols,
                start_dt,
                end_dt,
                initial_balance=initial_balance,
                fee_rate=fee_rate,
                slippage_bps=slippage_bps,
                filters_by_symbol=filters_by_symbol,
            )
            self._update_job(job_id, progress=85, message="Guardando reporte")
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


def _resolve_date_range(start_date: str | None, end_date: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if end_date:
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
    else:
        end_dt = now
    if start_date:
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    else:
        start_dt = end_dt - timedelta(days=LOOKBACK_DAYS_DEFAULT)
    return start_dt, end_dt


def _ensure_datastore_coverage(
    datastore: DataStore, symbols: Iterable[str], start_dt: datetime, end_dt: datetime
) -> None:
    missing = [symbol for symbol in symbols if not datastore.has_coverage(symbol, start_dt, end_dt)]
    if not missing:
        return
    warmup_minutes = int(os.getenv("SIM_WARMUP_MINUTES", "10"))
    recorder = BinanceHFRecorder(datastore=datastore)
    recorder.start(missing)
    warmup_end = datetime.now(timezone.utc) + timedelta(minutes=warmup_minutes)
    while datetime.now(timezone.utc) < warmup_end:
        time.sleep(1)
    recorder.stop()


def _load_exchange_filters() -> Dict[str, dict]:
    client = BinanceRestClient()
    exchange_info = client.get_json("/api/v3/exchangeInfo")
    return build_filters_from_exchange_info(exchange_info)


def _run_replay_backtest(
    datastore: DataStore,
    symbols: Iterable[str],
    start_dt: datetime,
    end_dt: datetime,
    *,
    initial_balance: float,
    fee_rate: float,
    slippage_bps: float,
    filters_by_symbol: Dict[str, dict],
) -> Dict[str, Any]:
    symbols_list = list(symbols)
    num_symbols = max(len(symbols_list), 1)
    cash_per_symbol = initial_balance / num_symbols
    initial_cash_by_symbol = {symbol: cash_per_symbol for symbol in symbols_list}
    engine = ReplayEngine(
        datastore,
        symbols_list,
        start_dt=start_dt,
        end_dt=end_dt,
    )
    simulator = ExecutionSimulator(
        initial_cash_by_symbol=initial_cash_by_symbol,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        filters_by_symbol=filters_by_symbol,
    )
    strategy = SimReplayStrategy(trade_notional=cash_per_symbol * 0.1)

    per_symbol = {
        symbol: {"symbol": symbol, "events": 0, "trades": 0, "skip_reason": None}
        for symbol in symbols_list
    }
    events_loaded_total = 0

    for event in engine.iter_events():
        state = engine.update_state(event)
        events_loaded_total += 1
        per_symbol[event.symbol]["events"] += 1

        orders = strategy.on_event(event, state)
        fills: List[Any] = []
        for order in orders:
            fills.extend(simulator.submit_order(order, state))

        fills.extend(simulator.on_event(state))
        for fill in fills:
            per_symbol[fill.symbol]["trades"] += 1
            strategy.on_fill(fill)

        simulator.record_equity(event.timestamp_us, engine.state_by_symbol)

    simulator.liquidate(engine.state_by_symbol)
    simulator.record_equity(int(end_dt.timestamp() * 1_000_000), engine.state_by_symbol)
    report = simulator.build_report()

    equity_df = pd.DataFrame(report.equity_curve)
    if not equity_df.empty:
        equity_df["timestamp"] = equity_df["timestamp"].apply(_format_time_us)
    summary = _calculate_summary(
        report.trades,
        equity_df,
        initial_balance=initial_balance,
    )
    diagnostics = _build_diagnostics(
        per_symbol=list(per_symbol.values()),
        events_loaded_total=events_loaded_total,
        trades_executed=len(report.trades),
    )
    return {
        "summary": summary,
        "equity": equity_df,
        "trades": report.trades,
        "diagnostics": diagnostics,
    }


def _calculate_summary(
    trades: List[Dict[str, Any]],
    equity_df: pd.DataFrame,
    initial_balance: float,
) -> Dict[str, Any]:
    final_balance = initial_balance
    if not equity_df.empty and "equity" in equity_df.columns:
        final_balance = float(equity_df["equity"].iloc[-1])
    total_pnl = final_balance - initial_balance
    total_return = total_pnl / initial_balance if initial_balance else 0
    num_trades = len(trades)
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
        "final_balance": final_balance,
        "total_return": total_return,
        "num_trades": num_trades,
        "winrate": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": max_drawdown,
    }


def _build_diagnostics(
    *,
    per_symbol: List[Dict[str, Any]],
    events_loaded_total: int,
    trades_executed: int,
) -> Dict[str, Any]:
    if trades_executed == 0:
        for item in per_symbol:
            item["skip_reason"] = _infer_skip_reason(item)

    return {
        "universe_size": len(per_symbol),
        "symbols_tested": sum(1 for item in per_symbol if item["events"] > 0),
        "data_source": "datastore_replay",
        "events_loaded_total": events_loaded_total,
        "trades_executed": trades_executed,
        "per_symbol": per_symbol,
    }


def _infer_skip_reason(symbol_diag: Dict[str, Any]) -> str:
    if symbol_diag["events"] == 0:
        return "no_data"
    if symbol_diag["trades"] == 0:
        return "filters_blocked"
    return "unknown"


def _save_report(report_dir: Path, result: Dict[str, Any]) -> None:
    summary_path = report_dir / "summary.json"
    equity_path = report_dir / "equity.csv"
    trades_path = report_dir / "trades.csv"

    summary_path.write_text(
        json.dumps(
            {
                "summary": result["summary"],
                "diagnostics": result["diagnostics"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    result["equity"].to_csv(equity_path, index=False)
    trades_df = pd.DataFrame(result["trades"])
    trades_df.to_csv(trades_path, index=False)


def _format_time_us(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value / 1_000_000).isoformat()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)
