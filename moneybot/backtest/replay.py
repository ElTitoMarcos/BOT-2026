from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable

import pandas as pd

from moneybot.data_provider import OHLCV_COLUMNS, interval_to_ms
from moneybot.datastore import DataStore, normalize_timestamp


def replay_from_datastore(
    datastore: DataStore,
    symbols: Iterable[str],
    *,
    start_dt: datetime,
    end_dt: datetime,
    interval: str,
) -> Dict[str, pd.DataFrame]:
    interval_ms = interval_to_ms(interval)
    start_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)
    data_by_symbol: Dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        rows = []
        current_bucket = None
        o = h = l = c = v = None
        for event in datastore.iter_events(symbol, "aggTrade", start_ts, end_ts):
            ts_ms = normalize_timestamp(event.get("T") or event.get("E"))
            if ts_ms < start_ts or ts_ms > end_ts:
                continue
            price_raw = event.get("p")
            qty_raw = event.get("q")
            try:
                price = float(price_raw)
                qty = float(qty_raw)
            except (TypeError, ValueError):
                continue
            bucket = ts_ms - (ts_ms % interval_ms)
            if current_bucket is None:
                current_bucket = bucket
                o = h = l = c = price
                v = qty
                continue
            if bucket != current_bucket:
                rows.append(
                    {
                        "timestamp": current_bucket,
                        "open": o,
                        "high": h,
                        "low": l,
                        "close": c,
                        "volume": v,
                    }
                )
                current_bucket = bucket
                o = h = l = c = price
                v = qty
                continue
            h = max(h, price)
            l = min(l, price)
            c = price
            v += qty
        if current_bucket is not None:
            rows.append(
                {
                    "timestamp": current_bucket,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                }
            )
        df = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
        data_by_symbol[symbol] = df

    return data_by_symbol


__all__ = ["replay_from_datastore"]
