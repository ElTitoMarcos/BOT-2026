from __future__ import annotations

from collections import deque
from pathlib import Path
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from moneybot.backtest.runner import BacktestJobManager
from moneybot.config import VALID_ENVIRONMENTS, get_config, load_env, save_config
from moneybot.data_provider import BinanceKlinesProvider
from moneybot.observability import ObservabilityStore
from moneybot.runtime import BotRuntime

app = FastAPI(title="MoneyBot")
runtime = BotRuntime()
observability = ObservabilityStore()
backtest_jobs = BacktestJobManager()
LOG_PATH = Path("logs/moneybot.log")
UI_DIR = Path(__file__).resolve().parent.parent / "ui_static"

load_env()


class ConfigPayload(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    env: Optional[str] = None
    persist: bool = True


class ModePayload(BaseModel):
    mode: Literal["SIM", "LIVE"]


class DataDownloadPayload(BaseModel):
    symbols: list[str]
    interval: str
    start_date: str
    end_date: str


class BacktestRunPayload(BaseModel):
    symbols: list[str]
    interval: str
    start_date: str
    end_date: str
    initial_balance: float = 1000.0
    fee_rate: float = 0.001
    slippage_bps: float = 0.0


@app.get("/", include_in_schema=False)
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/config/status")
def config_status() -> dict:
    config = get_config()
    return {
        "has_api_key": bool(config.get("BINANCE_API_KEY")),
        "env": config.get("ENV", "LIVE"),
    }


@app.post("/control/start")
def control_start() -> dict:
    runtime.start()
    return runtime.status()


@app.post("/control/stop")
def control_stop() -> dict:
    runtime.stop()
    return runtime.status()


@app.post("/control/set-mode")
def control_set_mode(payload: ModePayload) -> dict:
    runtime.set_mode(payload.mode)
    return runtime.status()


@app.get("/status")
def runtime_status() -> dict:
    return runtime.status()


@app.get("/metrics")
def metrics_status() -> dict:
    return observability.get_metrics()


@app.get("/trades")
def trades_status(limit: int = Query(50, ge=1, le=200)) -> dict:
    return {"trades": observability.get_trades(limit)}


@app.get("/logs/tail")
def logs_tail(limit: int = Query(200, ge=1, le=1000)) -> dict:
    if not LOG_PATH.exists():
        return {"lines": [], "available": False}
    try:
        with LOG_PATH.open("r", encoding="utf-8") as handle:
            lines = deque(handle, maxlen=limit)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo leer el log: {exc}") from exc
    return {"lines": [line.rstrip("\n") for line in lines], "available": True}


@app.post("/config/save")
def config_save(payload: ConfigPayload) -> dict:
    current = get_config()
    api_key = payload.api_key.strip() if payload.api_key else None
    api_secret = payload.api_secret.strip() if payload.api_secret else None
    env = payload.env.strip().upper() if payload.env else current.get("ENV", "LIVE")

    if api_key and api_key.startswith("****"):
        api_key = None

    if env not in VALID_ENVIRONMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"ENV inválido: {env}. Usa LIVE o TESTNET.",
        )

    if api_key is None:
        api_key = current.get("BINANCE_API_KEY")
    if api_secret is None:
        api_secret = current.get("BINANCE_API_SECRET")

    save_config(api_key, api_secret, env, persist=payload.persist)

    return {
        "has_api_key": bool(api_key),
        "env": env,
    }


@app.post("/data/download")
def data_download(payload: DataDownloadPayload) -> dict:
    if not payload.symbols:
        raise HTTPException(status_code=400, detail="Debe incluir al menos un símbolo.")
    try:
        start_dt = datetime.fromisoformat(payload.start_date).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(payload.end_date).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Fechas inválidas: {exc}",
        ) from exc
    if start_dt > end_dt:
        raise HTTPException(
            status_code=400,
            detail="start_date debe ser menor o igual que end_date",
        )

    provider = BinanceKlinesProvider()
    files: list[str] = []
    total_rows = 0
    for symbol in payload.symbols:
        df = provider.get_ohlcv(symbol, payload.interval, start_dt, end_dt)
        total_rows += len(df)
        files.append(str(provider.data_dir / provider._cache_filename(symbol, payload.interval)))
    return {"ok": True, "files": files, "rows": total_rows}


@app.get("/data/list")
def data_list() -> dict:
    data_dir = Path("./data")
    if not data_dir.exists():
        return {"files": []}
    files = sorted(
        str(path)
        for path in data_dir.iterdir()
        if path.is_file() and path.suffix in {".csv", ".parquet"}
    )
    return {"files": files}


@app.post("/backtest/run")
def backtest_run(payload: BacktestRunPayload) -> dict:
    job_id = backtest_jobs.run_job(payload.dict())
    return {"job_id": job_id}


@app.get("/backtest/status/{job_id}")
def backtest_status(job_id: str) -> dict:
    job = backtest_jobs.get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return {"state": job.state, "progress": job.progress, "message": job.message}


@app.get("/backtest/result/{job_id}")
def backtest_result(job_id: str) -> dict:
    job = backtest_jobs.get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.state != "completed":
        raise HTTPException(status_code=400, detail="El job no está completado")
    try:
        return backtest_jobs.read_results(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/backtest/download/{job_id}")
def backtest_download(job_id: str) -> FileResponse:
    job = backtest_jobs.get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.state != "completed":
        raise HTTPException(status_code=400, detail="El job no está completado")
    try:
        zip_path = backtest_jobs.build_zip(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(zip_path, filename=f"backtest_{job_id}.zip")


app.mount("/ui_static", StaticFiles(directory=UI_DIR), name="ui_static")


@app.get("/ui")
def ui_placeholder() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")
