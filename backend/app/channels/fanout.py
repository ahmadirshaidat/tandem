"""Wake subscribers after commit. The journal, not this transport, owns durability."""

import asyncio
import threading
from collections.abc import Callable
from typing import Protocol

from sqlalchemy import event
from sqlalchemy.orm import Session


class Fanout(Protocol):
    def listen(self, callback: Callable[[], None]) -> Callable[[], None]: ...
    def publish(self) -> None: ...


class MemoryFanout:
    def __init__(self):
        self.lock = threading.Lock()
        self.callbacks: set[Callable] = set()

    def listen(self, callback):
        with self.lock:
            self.callbacks.add(callback)

        def remove():
            with self.lock:
                self.callbacks.discard(callback)

        return remove

    def publish(self):
        with self.lock:
            callbacks = tuple(self.callbacks)
        for callback in callbacks:
            try:
                callback()
            except RuntimeError:
                pass  # Disconnected event loop; its connection removes this listener.

    def wake_event(self):
        wake = asyncio.Event()
        loop = asyncio.get_running_loop()
        remove = self.listen(lambda: loop.call_soon_threadsafe(wake.set))
        return wake, remove


fanout = MemoryFanout()


@event.listens_for(Session, "after_commit")
def committed(_session):
    # Includes membership changes, logout, reset, and refresh replay revocation.
    fanout.publish()
