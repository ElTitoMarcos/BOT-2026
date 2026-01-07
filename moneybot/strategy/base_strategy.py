from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from moneybot.models import Order


class BaseStrategy(ABC):
    @abstractmethod
    def on_event(self, event: dict, state: object) -> list[Order]:
        raise NotImplementedError

    @abstractmethod
    def on_fill(self, fill: Any) -> None:
        raise NotImplementedError
