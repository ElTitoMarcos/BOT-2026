from __future__ import annotations

import threading
import time
from typing import Optional


class BotRuntime:
    def __init__(self, mode: str = "PAPER") -> None:
        self.is_running = False
        self.is_paused = False
        self.mode = mode
        self.last_update_ts: Optional[float] = None
        self.stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self.stop_event.clear()
            self._pause_event.clear()
            self.is_paused = False
            self.is_running = True
            self.last_update_ts = time.time()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self.stop_event.set()
            self._pause_event.clear()
            self.is_paused = False
            thread = self._thread
            self._thread = None

        if thread and thread.is_alive():
            thread.join(timeout=5)
        self.is_running = False

    def pause(self) -> None:
        self._pause_event.set()
        self.is_paused = True

    def resume(self) -> None:
        self._pause_event.clear()
        self.is_paused = False

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def status(self) -> dict:
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "mode": self.mode,
            "last_update_ts": self.last_update_ts,
        }

    def _run_loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                if self._pause_event.is_set():
                    self.is_paused = True
                    time.sleep(0.2)
                    continue
                self.is_paused = False
                self.last_update_ts = time.time()
                time.sleep(1)
        finally:
            self.is_running = False
