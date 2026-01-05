from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Optional, Union

import pandas as pd
import requests

from .rate_limiter import BinanceRestClient, BinanceRateLimiter

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class IDataProvider(ABC):
    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        start_ts_ms: Union[int, float, str, pd.Timestamp],
        end_ts_ms: Union[int, float, str, pd.Timestamp],
    ) -> pd.DataFrame:
        raise NotImplementedError


def to_ms(value: Union[int, float, str, pd.Timestamp]) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    timestamp = pd.to_datetime(value, utc=True)
    return int(timestamp.timestamp() * 1000)


def normalize_float_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for column in columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype(float)
    return df


def interval_to_ms(interval: str) -> int:
    match = re.fullmatch(r"(\d+)([smhdwM])", interval)
    if not match:
        raise ValueError(f"Interval no soportado: {interval}")
    amount = int(match.group(1))
    unit = match.group(2)
    multipliers = {
        "s": 1000,
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
        "w": 7 * 24 * 60 * 60 * 1000,
        "M": 30 * 24 * 60 * 60 * 1000,
    }
    return amount * multipliers[unit]


@dataclass
class BinanceKlinesProvider(IDataProvider):
    base_url: str = "https://api.binance.com"
    data_dir: Path = Path("./data")
    session: Optional[requests.Session] = None
    rate_limiter: Optional[BinanceRateLimiter] = None
    rest_client: Optional[BinanceRestClient] = None

    def get_ohlcv(
        self,
        symbol: str,
        interval: str,
        start_ts_ms: Union[int, float, str, pd.Timestamp],
        end_ts_ms: Union[int, float, str, pd.Timestamp],
    ) -> pd.DataFrame:
        start_ms = to_ms(start_ts_ms)
        end_ms = to_ms(end_ts_ms)
        if start_ms > end_ms:
            raise ValueError("start_ts_ms debe ser menor o igual que end_ts_ms")

        self.data_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.data_dir / self._cache_filename(symbol, interval)

        cached = self._load_cache(cache_path)
        if cached.empty:
            data = self._fetch_range(symbol, interval, start_ms, end_ms)
        else:
            data = cached
            min_ts = int(data["timestamp"].min())
            max_ts = int(data["timestamp"].max())
            interval_ms = interval_to_ms(interval)

            if min_ts > start_ms:
                missing_start_end = min(end_ms, min_ts - interval_ms)
                if missing_start_end >= start_ms:
                    before = self._fetch_range(
                        symbol, interval, start_ms, missing_start_end
                    )
                    data = pd.concat([before, data], ignore_index=True)

            if max_ts < end_ms:
                missing_end_start = max(start_ms, max_ts + interval_ms)
                if missing_end_start <= end_ms:
                    after = self._fetch_range(
                        symbol, interval, missing_end_start, end_ms
                    )
                    data = pd.concat([data, after], ignore_index=True)

        data = data.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        data.reset_index(drop=True, inplace=True)
        data.to_csv(cache_path, index=False)
        requested = data[(data["timestamp"] >= start_ms) & (data["timestamp"] <= end_ms)]
        requested = requested.reset_index(drop=True)
        return requested[OHLCV_COLUMNS]

    def _cache_filename(self, symbol: str, interval: str) -> str:
        safe_symbol = symbol.replace("/", "-")
        return f"{safe_symbol}_{interval}.csv"

    def _load_cache(self, path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        if "timestamp" not in df.columns:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = df[OHLCV_COLUMNS]
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype(int)
        normalize_float_columns(df, ["open", "high", "low", "close", "volume"])
        return df

    def _fetch_range(
        self, symbol: str, interval: str, start_ms: int, end_ms: int
    ) -> pd.DataFrame:
        all_rows = []
        limit = 1000
        interval_ms = interval_to_ms(interval)
        current = start_ms
        session = self.session or requests.Session()
        rest_client = self.rest_client or BinanceRestClient(
            base_url=self.base_url,
            rate_limiter=self.rate_limiter,
            session=session,
        )

        while current <= end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current,
                "endTime": end_ms,
                "limit": limit,
            }
            rows = rest_client.get_json(
                "/api/v3/klines",
                params=params,
                weight=2,
            )
            if not rows:
                break
            all_rows.extend(rows)
            last_open_time = rows[-1][0]
            next_start = last_open_time + interval_ms
            if next_start <= current:
                break
            current = next_start
            if len(rows) < limit:
                break

        if not all_rows:
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        df = pd.DataFrame(
            [
                {
                    "timestamp": row[0],
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5],
                }
                for row in all_rows
            ]
        )
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype(int)
        normalize_float_columns(df, ["open", "high", "low", "close", "volume"])
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        df.reset_index(drop=True, inplace=True)
        return df
