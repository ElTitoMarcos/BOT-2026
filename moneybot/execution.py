from typing import Optional

from .models import Order


class ExecutionClient:
    def __init__(self, client=None) -> None:
        self.client = client

    def place_order(self, order: Order) -> Optional[Order]:
        if self.client is None:
            return None
        return order
