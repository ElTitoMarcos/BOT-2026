from __future__ import annotations

from typing import Any, Dict


class RiskManager:
    def __init__(self, **kwargs: Any) -> None:
        self.params: Dict[str, Any] = dict(kwargs)

    def should_enter(self, *_: Any, **__: Any) -> bool:
        return True

    def should_exit(self, *_: Any, **__: Any) -> bool:
        return False

    def apply(self, position: Any, candle: Any) -> None:
        pass
