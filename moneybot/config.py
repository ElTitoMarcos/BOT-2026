from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv, set_key

ENV_PATH = Path(".env")


def load_environment(env_path: Path | str = ENV_PATH) -> None:
    env_file = Path(env_path)
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)


def get_binance_credentials() -> Tuple[str | None, str | None]:
    return os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_API_SECRET")


def save_binance_credentials(
    api_key: str,
    api_secret: str,
    env_path: Path | str = ENV_PATH,
) -> None:
    env_file = Path(env_path)
    env_file.touch(exist_ok=True)
    set_key(str(env_file), "BINANCE_API_KEY", api_key)
    set_key(str(env_file), "BINANCE_API_SECRET", api_secret)
    os.environ["BINANCE_API_KEY"] = api_key
    os.environ["BINANCE_API_SECRET"] = api_secret
