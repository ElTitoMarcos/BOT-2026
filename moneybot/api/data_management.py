from __future__ import annotations

import os
import shutil
import tempfile
import threading
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from moneybot.config import DATA_MAX_GB
from moneybot.datastore import DataStore
from moneybot.market.recorder import BinanceHFRecorder

router = APIRouter()

_recorder_lock = threading.Lock()
_recorder: BinanceHFRecorder | None = None
_recorder_thread: threading.Thread | None = None
_recorder_stop_event: threading.Event | None = None


class RecordPayload(BaseModel):
    symbols: List[str] = Field(default_factory=list)
    streams: List[str] = Field(default_factory=list)


def get_datastore() -> DataStore:
    return DataStore()


def _data_dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for root, _dirs, files in os.walk(path):
        for filename in files:
            file_path = Path(root) / filename
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total


def _list_symbols(datastore: DataStore) -> list[str]:
    exchange_path = datastore.base_dir / datastore.exchange
    if not exchange_path.exists():
        return []
    symbols = [path.name for path in exchange_path.iterdir() if path.is_dir()]
    return sorted(symbols)


def _ensure_date_exists(datastore: DataStore, symbol: str, target: date) -> None:
    dates = datastore.available_dates(symbol)
    if target not in dates:
        raise HTTPException(
            status_code=404,
            detail=f"No hay datos para {symbol} en {target.isoformat()}",
        )


def _parse_date(date_str: str) -> date:
    try:
        return datetime.fromisoformat(date_str).date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Fecha inválida.") from exc


def _start_recorder(symbols: list[str], streams: list[str]) -> dict:
    global _recorder, _recorder_thread, _recorder_stop_event
    if not symbols:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un símbolo.")
    with _recorder_lock:
        if _recorder_thread and _recorder_thread.is_alive():
            raise HTTPException(status_code=400, detail="Grabación ya en curso.")
        recorder = BinanceHFRecorder()
        stop_event = threading.Event()

        def run() -> None:
            recorder.start_with_streams(symbols, streams)
            stop_event.wait()
            recorder.stop()

        thread = threading.Thread(target=run, daemon=True)
        _recorder = recorder
        _recorder_stop_event = stop_event
        _recorder_thread = thread
        thread.start()
    return {"status": "started", "symbols": symbols, "streams": streams}


def _stop_recorder() -> dict:
    global _recorder, _recorder_thread, _recorder_stop_event
    with _recorder_lock:
        if not (_recorder_thread and _recorder_thread.is_alive() and _recorder_stop_event):
            raise HTTPException(status_code=400, detail="No hay grabación activa.")
        _recorder_stop_event.set()
        _recorder_thread.join(timeout=5)
        _recorder = None
        _recorder_thread = None
        _recorder_stop_event = None
    return {"status": "stopped"}


@router.get("/symbols")
def list_symbols(datastore: DataStore = Depends(get_datastore)) -> dict:
    return {"symbols": _list_symbols(datastore)}


@router.get("/available-dates")
def available_dates(
    symbol: str = Query(..., min_length=1),
    datastore: DataStore = Depends(get_datastore),
) -> dict:
    dates = datastore.available_dates(symbol)
    return {"symbol": symbol.upper(), "dates": [item.isoformat() for item in dates]}


@router.get("/storage")
def storage_status(datastore: DataStore = Depends(get_datastore)) -> dict:
    size_bytes = _data_dir_size_bytes(datastore.base_dir)
    return {"size_bytes": size_bytes, "max_gb": DATA_MAX_GB}


@router.delete("/day")
def delete_day(
    symbol: str = Query(..., min_length=1),
    date_str: str = Query(..., alias="date", min_length=1),
    datastore: DataStore = Depends(get_datastore),
) -> dict:
    day = _parse_date(date_str)
    _ensure_date_exists(datastore, symbol, day)
    target_path = datastore.base_dir / datastore.exchange / symbol.upper() / day.isoformat()
    shutil.rmtree(target_path, ignore_errors=False)
    return {"deleted": True, "symbol": symbol.upper(), "date": day.isoformat()}


@router.post("/record/start")
def record_start(payload: RecordPayload) -> dict:
    symbols = [symbol.strip().upper() for symbol in payload.symbols if symbol.strip()]
    streams = [stream.strip() for stream in payload.streams if stream.strip()]
    return _start_recorder(symbols, streams)


@router.post("/record/stop")
def record_stop() -> dict:
    return _stop_recorder()


@router.get("/download")
def download_data(
    background_tasks: BackgroundTasks,
    symbol: str = Query(..., min_length=1),
    start: str = Query(..., min_length=1),
    end: str = Query(..., min_length=1),
    datastore: DataStore = Depends(get_datastore),
) -> FileResponse:
    symbol_upper = symbol.upper()
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="Rango de fechas inválido.")
    exchange_path = datastore.base_dir / datastore.exchange / symbol_upper
    if not exchange_path.exists():
        raise HTTPException(status_code=404, detail="Símbolo sin datos.")
    dates = [d for d in datastore.available_dates(symbol_upper) if start_date <= d <= end_date]
    if not dates:
        raise HTTPException(status_code=404, detail="No hay datos para el rango solicitado.")
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = Path(tmp_file.name)
    tmp_file.close()
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for day in dates:
            day_path = exchange_path / day.isoformat()
            if not day_path.exists():
                continue
            for file_path in day_path.iterdir():
                if file_path.is_file():
                    arcname = f"{symbol_upper}/{day.isoformat()}/{file_path.name}"
                    archive.write(file_path, arcname=arcname)
    background_tasks.add_task(tmp_path.unlink)
    filename = f"{symbol_upper}_{start_date.isoformat()}_{end_date.isoformat()}.zip"
    return FileResponse(tmp_path, filename=filename, media_type="application/zip")


__all__ = ["router"]
