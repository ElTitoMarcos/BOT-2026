from __future__ import annotations

from typing import Iterable, List, Optional

from moneybot.config import UNIVERSE_TOP_N
from moneybot.rate_limiter import BinanceRestClient


LEVERAGED_TOKENS = ("UP", "DOWN", "BULL", "BEAR")


def _is_leveraged_symbol(symbol: str) -> bool:
    upper_symbol = symbol.upper()
    return any(token in upper_symbol for token in LEVERAGED_TOKENS)


def build_universe(
    quote_asset: str = "BTC",
    *,
    top_n: Optional[int] = None,
    rest_client: Optional[BinanceRestClient] = None,
) -> List[str]:
    client = rest_client or BinanceRestClient()
    tickers = client.get_json("/api/v3/ticker/24hr")
    universe: List[tuple[str, float]] = []
    quote_asset = quote_asset.upper()
    limit = top_n if top_n is not None else UNIVERSE_TOP_N

    for ticker in tickers:
        symbol = str(ticker.get("symbol", "")).upper()
        if not symbol.endswith(quote_asset):
            continue
        if _is_leveraged_symbol(symbol):
            continue
        if "_" in symbol or ":" in symbol:
            continue
        try:
            quote_volume = float(ticker.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        universe.append((symbol, quote_volume))

    universe.sort(key=lambda item: item[1], reverse=True)
    return [symbol for symbol, _volume in universe[:limit]]


__all__ = ["build_universe"]
