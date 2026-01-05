from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Order:
    symbol: str
    side: str
    quantity: float
    price: Optional[float] = None
    order_id: Optional[str] = None


@dataclass
class Trade:
    symbol: str
    price: float
    quantity: float
    timestamp: datetime
    is_buyer: bool


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    current_price: Optional[float] = None
