from __future__ import annotations

from collections.abc import Iterator
from sys import platform
from threading import Event, Thread
from time import monotonic, sleep
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
        self._capture, first_frame, self.backend_name = self._open(camera_index)
        self._frames: LatestFrameQueue[tuple[Any, int]] = LatestFrameQueue()
        self._frames.put((first_frame, int(monotonic() * 1000)))
        self._stop = Event()
        self._thread = Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        self._thread.start()

    def _open(self, camera_index: int) -> tuple[Any, Any, str]:
        cv2 = self._cv2
        candidates: list[tuple[str, int]] = []
        if platform.startswith("win"):
            candidates.extend(
                (
                    ("DirectShow", cv2.CAP_DSHOW),
                    ("Media Foundation", cv2.CAP_MSMF),
                )
            )
        candidates.append(("automatic", cv2.CAP_ANY))
        failures: list[str] = []
        for name, backend in candidates:
            capture = cv2.VideoCapture(camera_index, backend)
            if not capture.isOpened():
                capture.release()
                failures.append(f"{name}: unavailable")
                continue
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            frame = None
            deadline = monotonic() + 2.0
            while monotonic() < deadline:
                ok, candidate = capture.read()
                if ok and candidate is not None:
                    frame = candidate
                    break
                sleep(0.03)
            if frame is not None:
                return capture, frame, name
            capture.release()
            failures.append(f"{name}: opened but returned no frames")
        details = "; ".join(failures)
        raise RuntimeError(f"Could not read camera {camera_index} ({details})")

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
