from __future__ import annotations

import threading
import time
from typing import Optional


class BotRuntime:
    def __init__(self, mode: str = "manual") -> None:
        self._mode = mode
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_update_ts: Optional[float] = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._pause_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            self._pause_event.clear()
            thread = self._thread
            self._thread = None

        if thread and thread.is_alive():
            thread.join(timeout=5)

    def pause(self) -> None:
        self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()

    def status(self) -> dict:
        thread = self._thread
        is_running = bool(thread and thread.is_alive())
        return {
            "is_running": is_running,
            "is_paused": bool(self._pause_event.is_set()),
            "mode": self._mode,
            "last_update_ts": self._last_update_ts,
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                time.sleep(0.2)
                continue
            self._last_update_ts = time.time()
            time.sleep(0.5)
