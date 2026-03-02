from __future__ import annotations

import threading
import time


class PauseController:
    def __init__(self) -> None:
        self._paused = False
        self._lock = threading.Lock()

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def wait_if_paused(self, cancel_event: threading.Event | None = None) -> None:
        while True:
            with self._lock:
                paused = self._paused
            if not paused:
                return
            if cancel_event is not None and cancel_event.is_set():
                return
            time.sleep(0.05)
