from __future__ import annotations

import json
from threading import Event, Lock

from .schemas import ProgressEvent


class RunBusyError(RuntimeError):
    """Raised when the presentation-safe active-run limit is reached."""


class RunRegistry:
    def __init__(self, *, max_active: int = 1) -> None:
        self.max_active = max_active
        self._runs: dict[str, Event] = {}
        self._lock = Lock()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._runs)

    def register(self, run_id: str) -> Event:
        with self._lock:
            if run_id in self._runs:
                raise RunBusyError(f"run is already active: {run_id}")
            if len(self._runs) >= self.max_active:
                raise RunBusyError("another screening run is active")
            token = Event()
            self._runs[run_id] = token
            return token

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            token = self._runs.get(run_id)
            if token is None:
                return False
            token.set()
            return True

    def finish(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)


def sse_encode(event: ProgressEvent) -> str:
    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"), allow_nan=False)
    return f"id: {event.sequence}\nevent: {event.event}\ndata: {payload}\n\n"
