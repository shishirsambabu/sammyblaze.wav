from __future__ import annotations

from collections.abc import Iterator
from time import monotonic
from typing import Any


def frames(camera_index: int = 0) -> Iterator[tuple[Any, int]]:
    """Yield latest camera frames; OpenCV remains an optional dependency."""
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the [vision] extra to use a camera") from exc
    capture = cv2.VideoCapture(camera_index)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open camera {camera_index}")
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            yield frame, int(monotonic() * 1000)
    finally:
        capture.release()
