from __future__ import annotations

from typing import Any


def draw_status(frame: Any, *, armed: bool, gesture: str, fps: float) -> Any:
    """Draw a minimal status overlay when OpenCV is available."""
    try:
        import cv2
    except ImportError:  # pragma: no cover - optional dependency
        return frame
    color = (50, 220, 50) if armed else (80, 80, 220)
    cv2.putText(
        frame,
        f"{'ARMED' if armed else 'DISARMED'} | {gesture} | {fps:.1f} FPS",
        (20, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
    )
    return frame
