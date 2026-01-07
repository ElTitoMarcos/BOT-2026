from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .accumulation_strategy import AccumulationStrategy
    from .base_strategy import BaseStrategy
    from .indicator_strategy import Strategy
    from .simple_strategy import SimReplayStrategy

__all__ = [
    "AccumulationStrategy",
    "BaseStrategy",
    "SimReplayStrategy",
    "Strategy",
]


def __getattr__(name: str) -> Any:
    if name == "AccumulationStrategy":
        from .accumulation_strategy import AccumulationStrategy

        return AccumulationStrategy
    if name == "BaseStrategy":
        from .base_strategy import BaseStrategy

        return BaseStrategy
    if name == "SimReplayStrategy":
        from .simple_strategy import SimReplayStrategy

        return SimReplayStrategy
    if name == "Strategy":
        from .indicator_strategy import Strategy

        return Strategy
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
