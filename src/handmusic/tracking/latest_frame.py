from __future__ import annotations

from threading import Condition
from time import monotonic
from typing import Generic, TypeVar

T = TypeVar("T")


class FrameStreamClosed(RuntimeError):
    """Raised when a frame stream has been closed and no frame remains."""


class LatestFrameQueue(Generic[T]):
    """A bounded one-item queue where the newest frame always wins."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._item: T | None = None
        self._closed = False

    def put(self, item: T) -> None:
        with self._condition:
            if self._closed:
                raise FrameStreamClosed("cannot put into a closed frame queue")
            self._item = item
            self._condition.notify()

    def get(self, timeout: float | None = None) -> T:
        deadline = None if timeout is None else monotonic() + timeout
        with self._condition:
            while self._item is None and not self._closed:
                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("timed out waiting for a camera frame")
                self._condition.wait(remaining)
            if self._item is not None:
                item, self._item = self._item, None
                return item
            raise FrameStreamClosed("frame stream is closed")

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
