from __future__ import annotations

from collections.abc import Iterator
from threading import Event, Thread
from time import monotonic
from typing import Any

from .latest_frame import FrameStreamClosed, LatestFrameQueue


class CameraStream:
    """Capture camera frames on a producer thread without creating a backlog."""

    def __init__(self, camera_index: int = 0) -> None:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Install the [vision] extra to use a camera") from exc
        self._cv2 = cv2
        self._capture = cv2.VideoCapture(camera_index)
        if not self._capture.isOpened():
            self._capture.release()
            raise RuntimeError(f"Could not open camera {camera_index}")
        self._frames: LatestFrameQueue[tuple[Any, int]] = LatestFrameQueue()
        self._stop = Event()
        self._thread = Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        self._thread.start()

    def _capture_loop(self) -> None:
        try:
            while not self._stop.is_set():
                ok, frame = self._capture.read()
                if not ok:
                    break
                try:
                    self._frames.put((frame, int(monotonic() * 1000)))
                except FrameStreamClosed:
                    break
        finally:
            self._frames.close()

    def __iter__(self) -> Iterator[tuple[Any, int]]:
        while True:
            try:
                yield self._frames.get()
            except FrameStreamClosed:
                return

    def close(self) -> None:
        self._stop.set()
        self._frames.close()
        self._capture.release()
        self._thread.join(timeout=1.0)


def frames(camera_index: int = 0) -> Iterator[tuple[Any, int]]:
    """Yield the newest available frame; OpenCV remains an optional dependency."""
    stream = CameraStream(camera_index)
    try:
        yield from stream
    finally:
        stream.close()
