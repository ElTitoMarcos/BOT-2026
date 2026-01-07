from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from moneybot.config import NOTIFICATION_WEBHOOK_URL


def send_notification(event: str, payload: Optional[dict[str, Any]] = None) -> None:
    url = NOTIFICATION_WEBHOOK_URL
    if not url:
        return
    body: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if payload:
        body["data"] = payload
    try:
        response = requests.post(url, json=body, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        logging.warning("No se pudo enviar notificación %s: %s", event, exc)
