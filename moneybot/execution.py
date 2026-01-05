import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import Order, Trade

try:
    from binance.exceptions import BinanceAPIException
except ImportError:  # pragma: no cover - optional dependency
    BinanceAPIException = None


SPOT_LIVE_REST_URL = "https://api.binance.com"
SPOT_LIVE_WS_URL = "wss://stream.binance.com:9443/ws"
SPOT_TESTNET_REST_URL = "https://testnet.binance.vision"
SPOT_TESTNET_WS_URL = "wss://testnet.binance.vision/ws"
VALID_ENVIRONMENTS = {"LIVE", "TESTNET"}


class LiveExecutor:
    def __init__(self, client=None) -> None:
        self.client = client
        self.environment = self._load_environment()
        if self.client is not None:
            self._configure_client_for_environment(self.client, self.environment)

    def place_order(self, order: Order) -> Optional[Order]:
        if self.client is None:
            return None
        if hasattr(self.client, "create_order"):
            response = self.client.create_order(
                order.symbol, "market", order.side, order.quantity, order.price
            )
            order.order_id = str(response.get("id")) if isinstance(response, dict) else None
        return order

    def healthcheck(self) -> Dict[str, str]:
        if self.client is None:
            raise RuntimeError("Healthcheck falló: cliente Binance no configurado.")

        self._check_server_time()
        account_info = self._check_account()
        self._check_permissions(account_info)

        return {
            "server_time": "OK",
            "account": "OK",
            "permissions": "OK",
        }

    def _load_environment(self) -> str:
        env = os.environ.get("ENV", "LIVE").upper()
        if env not in VALID_ENVIRONMENTS:
            raise ValueError(f"ENV inválido: {env}. Usa LIVE o TESTNET.")
        return env

    def _configure_client_for_environment(self, client: Any, env: str) -> None:
        rest_url, ws_url = self._urls_for_env(env)
        if hasattr(client, "API_URL"):
            client.API_URL = f"{rest_url}/api"
        if hasattr(client, "WS_API_URL"):
            client.WS_API_URL = ws_url
        if hasattr(client, "WS_URL"):
            client.WS_URL = ws_url
        if hasattr(client, "STREAM_URL"):
            client.STREAM_URL = ws_url
        if hasattr(client, "testnet"):
            client.testnet = env == "TESTNET"

    def _urls_for_env(self, env: str) -> Tuple[str, str]:
        if env == "TESTNET":
            return SPOT_TESTNET_REST_URL, SPOT_TESTNET_WS_URL
        return SPOT_LIVE_REST_URL, SPOT_LIVE_WS_URL

    def _check_server_time(self) -> None:
        try:
            self.client.get_server_time()
        except Exception as exc:
            raise RuntimeError(f"Healthcheck falló: server time error. {exc}") from exc

    def _check_account(self) -> Dict[str, Any]:
        try:
            return self.client.get_account()
        except Exception as exc:
            raise RuntimeError(
                f"Healthcheck falló: account endpoint error. {self._diagnose_auth_error(exc)}"
            ) from exc

    def _check_permissions(self, account_info: Dict[str, Any]) -> None:
        can_trade = account_info.get("canTrade", True)
        if not can_trade:
            raise RuntimeError(
                "Healthcheck falló: permisos insuficientes (canTrade=false). "
                "Habilita trading en la API key."
            )

    def _diagnose_auth_error(self, exc: Exception) -> str:
        message = str(exc)
        code = getattr(exc, "code", None)
        if BinanceAPIException is not None and isinstance(exc, BinanceAPIException):
            message = getattr(exc, "message", message)
        if code in (-2014, -2015):
            return (
                f"{message} (code {code}). "
                "La API key es inválida o la IP no está autorizada. "
                "Verifica key/secret y la whitelist de IP."
            )
        if code == -2010:
            return (
                f"{message} (code {code}). "
                "Permisos insuficientes para operar en Spot. "
                "Activa trading en la API key."
            )
        if "IP" in message or "whitelist" in message:
            return (
                f"{message}. Revisa restricciones de IP en la API key."
            )
        if "Invalid API-key" in message or "invalid api key" in message.lower():
            return (
                f"{message}. Verifica que la API key/secret sean correctas."
            )
        return message


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
