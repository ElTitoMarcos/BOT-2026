from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from moneybot.backtest.runner import BacktestJobManager
from moneybot.config import VALID_ENVIRONMENTS, get_config, load_env, save_config
from moneybot.observability import ObservabilityStore
from moneybot.runtime import BotRuntime

app = FastAPI(title="MoneyBot")
runtime = BotRuntime()
observability = ObservabilityStore()
backtest_jobs = BacktestJobManager()
LOG_PATH = Path("logs/moneybot.log")
UI_DIR = Path(__file__).resolve().parent.parent / "ui_static"
CLIENT_CHECK_INTERVAL_S = 5
CLIENT_TIMEOUT_S = 15

load_env()


async def _monitor_ui_clients() -> None:
    while True:
        await asyncio.sleep(CLIENT_CHECK_INTERVAL_S)
        last_seen = getattr(app.state, "last_client_seen", None)
        if last_seen is None:
            continue
        if time.time() - last_seen > CLIENT_TIMEOUT_S:
            runtime.stop()
            server = getattr(app.state, "server", None)
            if server is not None:
                server.should_exit = True
            break


@app.on_event("startup")
async def startup_tasks() -> None:
    app.state.last_client_seen = time.time()
    app.state.monitor_task = asyncio.create_task(_monitor_ui_clients())


@app.on_event("shutdown")
async def shutdown_tasks() -> None:
    monitor_task = getattr(app.state, "monitor_task", None)
    if monitor_task is not None:
        monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor_task


class ConfigPayload(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    env: Optional[str] = None
    persist: bool = True


class ModePayload(BaseModel):
    mode: Literal["SIM", "LIVE"]


class BacktestRunPayload(BaseModel):
    symbols: Optional[list[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
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


@app.post("/ui/heartbeat")
def ui_heartbeat() -> dict:
    app.state.last_client_seen = time.time()
    return {"ok": True}


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


@app.post("/backtest/run")
def backtest_run(payload: BacktestRunPayload) -> dict:
    job_id = backtest_jobs.run_job(payload.dict(exclude_none=True))
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
