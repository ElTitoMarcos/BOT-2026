from __future__ import annotations

import gzip
import importlib.util
import io
import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Iterable, Optional

from moneybot.config import DATA_MAX_GB

if importlib.util.find_spec("zstandard"):
    import zstandard as zstd
else:  # pragma: no cover - optional dependency
    zstd = None

COMPRESSED_EXT = "zst" if zstd is not None else "gz"
STREAM_FILES = {
    "aggTrade": f"aggTrade.jsonl.{COMPRESSED_EXT}",
    "depth": f"depth.jsonl.{COMPRESSED_EXT}",
    "bookTicker": f"bookTicker.jsonl.{COMPRESSED_EXT}",
}


@dataclass
class DataBudgetManager:
    data_dir: Path
    max_gb: float = DATA_MAX_GB
    check_interval_s: float = 60.0

    def __post_init__(self) -> None:
        self._last_check = 0.0
        self._lock = threading.Lock()

    def enforce_budget(self) -> None:
        now = time.monotonic()
        if now - self._last_check < self.check_interval_s:
            return
        with self._lock:
            now = time.monotonic()
            if now - self._last_check < self.check_interval_s:
                return
            self._last_check = now
            self._enforce_locked()

    def _enforce_locked(self) -> None:
        total_bytes = self._total_size_bytes()
        max_bytes = self.max_gb * 1024 * 1024 * 1024
        if total_bytes <= max_bytes:
            return
        day_dirs = self._collect_day_dirs()
        for _, day_path in day_dirs:
            if total_bytes <= max_bytes:
                break
            size = self._dir_size(day_path)
            shutil.rmtree(day_path, ignore_errors=True)
            total_bytes -= size

    def _total_size_bytes(self) -> int:
        total = 0
        for root, _dirs, files in os.walk(self.data_dir):
            for filename in files:
                path = Path(root) / filename
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total

    def _collect_day_dirs(self) -> list[tuple[date, Path]]:
        day_dirs: list[tuple[date, Path]] = []
        if not self.data_dir.exists():
            return day_dirs
        for exchange_path in self.data_dir.iterdir():
            if not exchange_path.is_dir():
                continue
            for symbol_path in exchange_path.iterdir():
                if not symbol_path.is_dir():
                    continue
                for day_path in symbol_path.iterdir():
                    if not day_path.is_dir():
                        continue
                    try:
                        day = datetime.strptime(day_path.name, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    day_dirs.append((day, day_path))
        day_dirs.sort(key=lambda item: item[0])
        return day_dirs

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        for root, _dirs, files in os.walk(path):
            for filename in files:
                file_path = Path(root) / filename
                try:
                    total += file_path.stat().st_size
                except OSError:
                    continue
        return total


class DataStore:
    def __init__(
        self,
        base_dir: Path | str = Path("./data"),
        exchange: str = "binance",
        *,
        budget_manager: Optional[DataBudgetManager] = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.exchange = exchange
        self.budget_manager = budget_manager or DataBudgetManager(self.base_dir)
        self._lock = threading.Lock()

    def write_event(self, symbol: str, stream: str, payload: dict, event_ts_ms: int) -> None:
        symbol = symbol.upper()
        day = datetime.fromtimestamp(event_ts_ms / 1000, tz=timezone.utc).date()
        dir_path = self.base_dir / self.exchange / symbol / day.isoformat()
        dir_path.mkdir(parents=True, exist_ok=True)
        filename = STREAM_FILES.get(stream, f"{stream}.jsonl.zst")
        file_path = dir_path / filename
        with self._open_writer(file_path) as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.budget_manager.enforce_budget()

    def iter_events(
        self,
        symbol: str,
        stream: str,
        start_ts_ms: int,
        end_ts_ms: int,
    ) -> Generator[dict, None, None]:
        symbol = symbol.upper()
        start_day = datetime.fromtimestamp(start_ts_ms / 1000, tz=timezone.utc).date()
        end_day = datetime.fromtimestamp(end_ts_ms / 1000, tz=timezone.utc).date()
        for day in self._iter_days(start_day, end_day):
            file_path = self.base_dir / self.exchange / symbol / day.isoformat() / STREAM_FILES.get(
                stream, f"{stream}.jsonl.zst"
            )
            if not file_path.exists():
                continue
            with self._open_reader(file_path) as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    yield data

    def available_dates(self, symbol: str) -> list[date]:
        symbol_path = self.base_dir / self.exchange / symbol.upper()
        if not symbol_path.exists():
            return []
        dates: list[date] = []
        for day_path in symbol_path.iterdir():
            if not day_path.is_dir():
                continue
            try:
                dates.append(datetime.strptime(day_path.name, "%Y-%m-%d").date())
            except ValueError:
                continue
        return sorted(dates)

    def available_range(self, symbol: str) -> tuple[datetime | None, datetime | None]:
        dates = self.available_dates(symbol)
        if not dates:
            return None, None
        start_date = dates[0]
        end_date = dates[-1]
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        return start_dt, end_dt

    def has_coverage(self, symbol: str, start_dt: datetime, end_dt: datetime) -> bool:
        dates = self.available_dates(symbol)
        if not dates:
            return False
        needed_dates = set(self._iter_days(start_dt.date(), end_dt.date()))
        return needed_dates.issubset(set(dates))

    @contextmanager
    def _open_writer(self, path: Path):
        if zstd is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab") as file_handle:
                cctx = zstd.ZstdCompressor(level=3)
                with cctx.stream_writer(file_handle) as writer:
                    with io.TextIOWrapper(writer, encoding="utf-8") as text_wrapper:
                        yield text_wrapper
                    writer.flush(zstd.FLUSH_FRAME)
        else:
            with gzip.open(path, "at", encoding="utf-8") as handle:
                yield handle

    @contextmanager
    def _open_reader(self, path: Path):
        if zstd is not None:
            with path.open("rb") as file_handle:
                dctx = zstd.ZstdDecompressor()
                with dctx.stream_reader(file_handle) as reader:
                    text_wrapper = io.TextIOWrapper(reader, encoding="utf-8")
                    yield text_wrapper
        else:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                yield handle

    @staticmethod
    def _iter_days(start_day: date, end_day: date) -> Iterable[date]:
        current = start_day
        while current <= end_day:
            yield current
            current += timedelta(days=1)


def normalize_timestamp(value: int | float | str | None) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            return 0
    if isinstance(value, float):
        value = int(value)
    if value > 1e14:
        return int(value / 1000)
    return int(value)


__all__ = ["DataStore", "DataBudgetManager", "normalize_timestamp"]
