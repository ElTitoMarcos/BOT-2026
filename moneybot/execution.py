import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import Order, Trade


class LiveExecutor:
    def __init__(self, client=None) -> None:
        self.client = client

    def place_order(self, order: Order) -> Optional[Order]:
        if self.client is None:
            return None
        if hasattr(self.client, "create_order"):
            response = self.client.create_order(
                order.symbol, "market", order.side, order.quantity, order.price
            )
            order.order_id = str(response.get("id")) if isinstance(response, dict) else None
        return order


class PaperExecutor:
    def __init__(
        self,
        state_path: str = "./state/paper_wallet.json",
        starting_balances: Optional[Dict[str, float]] = None,
    ) -> None:
        self.state_path = Path(state_path)
        self.balances: Dict[str, float] = {}
        self.trades: List[Trade] = []
        self._load_state(starting_balances)

    def place_order(self, order: Order) -> Optional[Order]:
        if order.price is None:
            return None

        base_asset, quote_asset = self._split_symbol(order.symbol)
        side = order.side.upper()
        cost = order.quantity * order.price

        if side == "BUY":
            if self.balances.get(quote_asset, 0.0) < cost:
                return None
            self.balances[quote_asset] = self.balances.get(quote_asset, 0.0) - cost
            self.balances[base_asset] = self.balances.get(base_asset, 0.0) + order.quantity
            is_buyer = True
        elif side == "SELL":
            if self.balances.get(base_asset, 0.0) < order.quantity:
                return None
            self.balances[base_asset] = self.balances.get(base_asset, 0.0) - order.quantity
            self.balances[quote_asset] = self.balances.get(quote_asset, 0.0) + cost
            is_buyer = False
        else:
            return None

        order.order_id = order.order_id or str(uuid.uuid4())
        trade = Trade(
            symbol=order.symbol,
            price=order.price,
            quantity=order.quantity,
            timestamp=datetime.utcnow(),
            is_buyer=is_buyer,
        )
        self.trades.append(trade)
        self._save_state()
        return order

    def _load_state(self, starting_balances: Optional[Dict[str, float]]) -> None:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.balances = data.get("balances", {})
            trades_data = data.get("trades", [])
            self.trades = [self._trade_from_dict(trade) for trade in trades_data]
            return

        self.balances = starting_balances or {"USDT": 0.0}
        self.trades = []
        self._save_state()

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "balances": self.balances,
            "trades": [self._trade_to_dict(trade) for trade in self.trades],
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _trade_to_dict(self, trade: Trade) -> Dict[str, Any]:
        data = asdict(trade)
        data["timestamp"] = trade.timestamp.isoformat()
        return data

    def _trade_from_dict(self, data: Dict[str, Any]) -> Trade:
        return Trade(
            symbol=data["symbol"],
            price=float(data["price"]),
            quantity=float(data["quantity"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_buyer=bool(data["is_buyer"]),
        )

    def _split_symbol(self, symbol: str) -> Tuple[str, str]:
        if "/" in symbol:
            base, quote = symbol.split("/", maxsplit=1)
            return base, quote

        known_quotes = ("USDT", "BUSD", "USDC", "BTC", "ETH", "BNB", "EUR", "USD")
        for quote in known_quotes:
            if symbol.endswith(quote):
                return symbol[: -len(quote)], quote

        midpoint = len(symbol) // 2
        return symbol[:midpoint], symbol[midpoint:]


ExecutionClient = LiveExecutor
