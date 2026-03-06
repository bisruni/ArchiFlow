"""Thread-safe pause/resume primitive for long-running operations."""

from __future__ import annotations

import threading
import time


class PauseController:
    """Coordinate paused state between UI and worker threads."""

    def __init__(self) -> None:
        """Create controller in resumed state."""
        self._paused = False
        self._lock = threading.Lock()

    def pause(self) -> None:
        """Mark controller state as paused."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Clear paused state and allow progress."""
        with self._lock:
            self._paused = False

    def wait_if_paused(self, cancel_event: threading.Event | None = None) -> None:
        """Block in short intervals while paused, unless cancelled."""
        while True:
            with self._lock:
                paused = self._paused
            if not paused:
                return
            if cancel_event is not None and cancel_event.is_set():
                return
            time.sleep(0.05)
