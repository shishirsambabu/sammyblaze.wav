from __future__ import annotations

from collections.abc import Callable, Iterator
from math import isfinite
from sys import platform
from threading import BoundedSemaphore, Event, Lock, Thread
from time import monotonic, sleep
from typing import Any

from .latest_frame import FrameStreamClosed, LatestFrameQueue

DEFAULT_OPEN_TIMEOUT_S = 4.5
_OPEN_POLL_INTERVAL_S = 0.02
_FRAME_POLL_INTERVAL_S = 0.05
_MAX_OPEN_WORKERS = 3
_OPEN_WORKER_SLOTS = BoundedSemaphore(_MAX_OPEN_WORKERS)


class CameraOpenCancelled(RuntimeError):
    """Raised when camera startup is cancelled before the first frame."""


class _OpenResult:
    """Synchronize ownership of a capture returned by a bounded open worker."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.done = Event()
        self.abandoned = False
        self.capture: Any | None = None
        self.frame: Any | None = None
        self.failure: str | None = None

    def abandon(self) -> Any | None:
        """Prevent a late result from escaping and return any result already published."""
        with self.lock:
            self.abandoned = True
            capture, self.capture = self.capture, None
            self.frame = None
            return capture

    def take(self) -> tuple[Any | None, Any | None, str | None]:
        with self.lock:
            capture, self.capture = self.capture, None
            frame, self.frame = self.frame, None
            return capture, frame, self.failure


def _release_capture(capture: Any | None) -> None:
    if capture is None:
        return
    try:
        capture.release()
    except Exception:
        # Cleanup must not hide the original open failure.
        pass


def _open_candidate_worker(
    *,
    cv2: Any,
    camera_index: int,
    backend: int,
    deadline: float,
    result: _OpenResult,
    stop_requested: Callable[[], bool],
) -> None:
    """Open one backend without allowing its native call to block the caller."""
    capture = None
    frame = None
    failure = None
    publish_capture = False
    try:
        try:
            capture = cv2.VideoCapture(camera_index, backend)
            if not capture.isOpened():
                failure = "unavailable"
            else:
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                while monotonic() < deadline and not stop_requested():
                    ok, candidate = capture.read()
                    if ok and candidate is not None:
                        frame = candidate
                        break
                    sleep(0.03)
                if frame is None:
                    failure = (
                        "cancelled"
                        if stop_requested()
                        else "opened but returned no frames"
                    )
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"

        with result.lock:
            if not result.abandoned and frame is not None:
                result.capture = capture
                result.frame = frame
                result.failure = None
                publish_capture = True
            elif not result.abandoned:
                result.failure = failure or "unavailable"
    finally:
        if not publish_capture:
            _release_capture(capture)
        result.done.set()
        _OPEN_WORKER_SLOTS.release()


class CameraStream:
    """Capture camera frames on a producer thread without creating a backlog."""

    def __init__(
        self,
        camera_index: int = 0,
        *,
        stop_event: Event | None = None,
        open_timeout_s: float = DEFAULT_OPEN_TIMEOUT_S,
    ) -> None:
        if not isfinite(open_timeout_s) or open_timeout_s <= 0:
            raise ValueError("open_timeout_s must be a positive finite number")
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Install the [vision] extra to use a camera") from exc
        self._cv2 = cv2
        self._external_stop = stop_event
        self._closed = Event()
        self._capture, first_frame, self.backend_name = self._open(
            camera_index,
            open_timeout_s,
        )
        self._frames: LatestFrameQueue[tuple[Any, int]] = LatestFrameQueue()
        self._frames.put((first_frame, int(monotonic() * 1000)))
        self._thread = Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        self._thread.start()

    def _stop_requested(self) -> bool:
        return self._closed.is_set() or (
            self._external_stop is not None and self._external_stop.is_set()
        )

    def _open(
        self,
        camera_index: int,
        open_timeout_s: float,
    ) -> tuple[Any, Any, str]:
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
        strategy_deadline = monotonic() + open_timeout_s
        failures: list[str] = []
        for index, (name, backend) in enumerate(candidates):
            if self._stop_requested():
                raise CameraOpenCancelled(f"Camera {camera_index} open cancelled")
            remaining = strategy_deadline - monotonic()
            if remaining <= 0:
                failures.append(f"{name}: total open deadline expired")
                break
            attempts_left = len(candidates) - index
            attempt_timeout = remaining / attempts_left
            attempt_deadline = monotonic() + attempt_timeout
            if not _OPEN_WORKER_SLOTS.acquire(blocking=False):
                failures.append(f"{name}: open worker capacity exhausted")
                continue

            result = _OpenResult()
            worker = Thread(
                target=_open_candidate_worker,
                kwargs={
                    "cv2": cv2,
                    "camera_index": camera_index,
                    "backend": backend,
                    "deadline": attempt_deadline,
                    "result": result,
                    "stop_requested": self._stop_requested,
                },
                name=f"camera-open-{name.lower().replace(' ', '-')}",
                daemon=True,
            )
            try:
                worker.start()
            except Exception:
                _OPEN_WORKER_SLOTS.release()
                raise

            while not result.done.is_set():
                if self._stop_requested():
                    _release_capture(result.abandon())
                    raise CameraOpenCancelled(f"Camera {camera_index} open cancelled")
                remaining_attempt = attempt_deadline - monotonic()
                if remaining_attempt <= 0:
                    break
                result.done.wait(min(_OPEN_POLL_INTERVAL_S, remaining_attempt))

            if not result.done.is_set():
                _release_capture(result.abandon())
                failures.append(f"{name}: timed out after {attempt_timeout:.2f}s")
                continue

            capture, frame, failure = result.take()
            if self._stop_requested():
                _release_capture(capture)
                raise CameraOpenCancelled(f"Camera {camera_index} open cancelled")
            if capture is not None and frame is not None:
                return capture, frame, name
            failures.append(f"{name}: {failure or 'unavailable'}")
        details = "; ".join(failures)
        raise RuntimeError(f"Could not read camera {camera_index} ({details})")

    def _capture_loop(self) -> None:
        try:
            while not self._stop_requested():
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
        while not self._stop_requested():
            try:
                yield self._frames.get(timeout=_FRAME_POLL_INTERVAL_S)
            except TimeoutError:
                continue
            except FrameStreamClosed:
                return

    def close(self) -> None:
        self._closed.set()
        self._frames.close()
        self._capture.release()
        self._thread.join(timeout=1.0)


def frames(
    camera_index: int = 0,
    *,
    stop_event: Event | None = None,
    open_timeout_s: float = DEFAULT_OPEN_TIMEOUT_S,
) -> Iterator[tuple[Any, int]]:
    """Yield the newest available frame; OpenCV remains an optional dependency."""
    stream = CameraStream(
        camera_index,
        stop_event=stop_event,
        open_timeout_s=open_timeout_s,
    )
    try:
        yield from stream
    finally:
        stream.close()
