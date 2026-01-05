import logging
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)

_client = None
_symbol_filters = {}


def configure(client):
    global _client
    _client = client
    _symbol_filters.clear()


def _ensure_exchange_info():
    if _client is None:
        raise RuntimeError("Binance client no configurado para exchange_filters.")
    if _symbol_filters:
        return
    exchange_info = _client.get_exchange_info()
    for symbol_info in exchange_info.get("symbols", []):
        filters = {f["filterType"]: f for f in symbol_info.get("filters", [])}
        _symbol_filters[symbol_info.get("symbol")] = filters


def _get_filter(symbol, filter_type):
    _ensure_exchange_info()
    symbol_filters = _symbol_filters.get(symbol)
    if not symbol_filters:
        logger.warning("Filtros no encontrados para el símbolo %s.", symbol)
        return None
    return symbol_filters.get(filter_type)


def _to_decimal(value):
    return Decimal(str(value))


def adjust_qty(symbol, qty):
    lot_size = _get_filter(symbol, "LOT_SIZE")
    if not lot_size:
        logger.warning("No se encontró filtro LOT_SIZE para %s.", symbol)
        return qty

    min_qty = _to_decimal(lot_size["minQty"])
    max_qty = _to_decimal(lot_size["maxQty"])
    step_size = _to_decimal(lot_size["stepSize"])
    qty_dec = _to_decimal(qty)

    if qty_dec < min_qty or qty_dec > max_qty:
        logger.warning(
            "Cantidad %s fuera de rango [%s, %s] para %s.",
            qty_dec,
            min_qty,
            max_qty,
            symbol,
        )

    bounded = min(max(qty_dec, min_qty), max_qty)
    steps = (bounded / step_size).to_integral_value(rounding=ROUND_DOWN)
    adjusted = (steps * step_size).quantize(step_size)

    if adjusted < min_qty or adjusted > max_qty or adjusted == 0:
        logger.warning(
            "Cantidad ajustada %s inválida para %s (min %s, max %s, step %s).",
            adjusted,
            symbol,
            min_qty,
            max_qty,
            step_size,
        )
        return None

    return float(adjusted)


def adjust_price(symbol, price):
    price_filter = _get_filter(symbol, "PRICE_FILTER")
    if not price_filter:
        logger.warning("No se encontró filtro PRICE_FILTER para %s.", symbol)
        return price

    min_price = _to_decimal(price_filter["minPrice"])
    max_price = _to_decimal(price_filter["maxPrice"])
    tick_size = _to_decimal(price_filter["tickSize"])
    price_dec = _to_decimal(price)

    if price_dec < min_price or price_dec > max_price:
        logger.warning(
            "Precio %s fuera de rango [%s, %s] para %s.",
            price_dec,
            min_price,
            max_price,
            symbol,
        )

    steps = (price_dec / tick_size).to_integral_value(rounding=ROUND_DOWN)
    adjusted = (steps * tick_size).quantize(tick_size)

    if adjusted <= 0:
        logger.warning("Precio ajustado %s inválido para %s.", adjusted, symbol)
        return None

    return float(adjusted)


def validate_min_notional(symbol, price, qty):
    min_notional_filter = _get_filter(symbol, "MIN_NOTIONAL")
    if not min_notional_filter:
        return True

    min_notional = _to_decimal(min_notional_filter["minNotional"])
    notional = _to_decimal(price) * _to_decimal(qty)

    if notional < min_notional:
        logger.warning(
            "Valor nominal %s inferior al mínimo %s para %s.",
            notional,
            min_notional,
            symbol,
        )
        return False

    return True
