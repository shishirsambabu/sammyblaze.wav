from __future__ import annotations

from typing import Any

from handmusic.common.models import HandObservation

HAND_CONNECTIONS = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (13, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (0, 17),
)


def draw_landmarks(frame: Any, observations: list[HandObservation]) -> Any:
    """Draw normalized hand skeletons and confidence without leaking vendor types."""
    try:
        import cv2
    except ImportError:  # pragma: no cover - optional dependency
        return frame
    height, width = frame.shape[:2]
    for observation in observations:
        points = [(int(point.x * width), int(point.y * height)) for point in observation.landmarks]
        color = (50, 220, 50) if observation.handedness == "left" else (220, 180, 50)
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, points[start], points[end], color, 2)
        for point in points:
            cv2.circle(frame, point, 4, color, -1)
        wrist_x, wrist_y = points[0]
        cv2.putText(
            frame,
            f"{observation.handedness} {observation.confidence:.2f}",
            (wrist_x + 8, wrist_y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )
    return frame


def draw_status(
    frame: Any,
    *,
    armed: bool,
    gesture: str,
    chord: str,
    fps: float,
    hands: int = 0,
) -> Any:
    """Draw a minimal status overlay when OpenCV is available."""
    try:
        import cv2
    except ImportError:  # pragma: no cover - optional dependency
        return frame
    color = (50, 220, 50) if armed else (80, 80, 220)
    cv2.putText(
        frame,
        f"{'ARMED' if armed else 'DISARMED'} | {chord} | {gesture} | {hands} hands | {fps:.1f} FPS",
        (20, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
    )
    return frame
