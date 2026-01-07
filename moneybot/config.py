from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv, set_key

ENV_PATH = Path(".env")
VALID_ENVIRONMENTS = {"LIVE", "TESTNET"}
DATA_MAX_GB = float(os.getenv("DATA_MAX_GB", "100"))
HF_INTERVAL = os.getenv("HF_INTERVAL", "1s")
DEPTH_SPEED = os.getenv("DEPTH_SPEED", "100ms")
UNIVERSE_TOP_N = int(os.getenv("UNIVERSE_TOP_N", "30"))
LOOKBACK_DAYS_DEFAULT = int(os.getenv("LOOKBACK_DAYS_DEFAULT", "30"))


def load_env(env_path: Path | str = ENV_PATH) -> None:
    env_file = Path(env_path)
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)


def get_config() -> Dict[str, Optional[str]]:
    return {
        "BINANCE_API_KEY": os.environ.get("BINANCE_API_KEY"),
        "BINANCE_API_SECRET": os.environ.get("BINANCE_API_SECRET"),
        "ENV": os.environ.get("ENV", "LIVE").upper(),
        "LIVE_WS_URL": os.environ.get("LIVE_WS_URL"),
        "TESTNET_WS_URL": os.environ.get("TESTNET_WS_URL"),
    }


def save_config(
    api_key: Optional[str],
    api_secret: Optional[str],
    env: Optional[str],
    live_ws_url: Optional[str] = None,
    testnet_ws_url: Optional[str] = None,
    env_path: Path | str = ENV_PATH,
    persist: bool = True,
) -> None:
    if env is not None:
        normalized_env = env.upper()
        if normalized_env not in VALID_ENVIRONMENTS:
            raise ValueError(f"ENV inválido: {normalized_env}. Usa LIVE o TESTNET.")
        env = normalized_env

    if persist:
        env_file = Path(env_path)
        env_file.touch(exist_ok=True)
        if api_key is not None:
            set_key(str(env_file), "BINANCE_API_KEY", api_key)
        if api_secret is not None:
            set_key(str(env_file), "BINANCE_API_SECRET", api_secret)
        if env is not None:
            set_key(str(env_file), "ENV", env)
        if live_ws_url is not None:
            set_key(str(env_file), "LIVE_WS_URL", live_ws_url)
        if testnet_ws_url is not None:
            set_key(str(env_file), "TESTNET_WS_URL", testnet_ws_url)

    if api_key is not None:
        os.environ["BINANCE_API_KEY"] = api_key
    if api_secret is not None:
        os.environ["BINANCE_API_SECRET"] = api_secret
    if env is not None:
        os.environ["ENV"] = env
    if live_ws_url is not None:
        os.environ["LIVE_WS_URL"] = live_ws_url
    if testnet_ws_url is not None:
        os.environ["TESTNET_WS_URL"] = testnet_ws_url


__all__ = [
    "DATA_MAX_GB",
    "DEPTH_SPEED",
    "ENV_PATH",
    "HF_INTERVAL",
    "LOOKBACK_DAYS_DEFAULT",
    "UNIVERSE_TOP_N",
    "VALID_ENVIRONMENTS",
    "get_config",
    "load_env",
    "save_config",
]
