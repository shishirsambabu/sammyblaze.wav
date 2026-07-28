from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from handmusic.common.models import HandObservation, Point3D


@dataclass(frozen=True, slots=True)
class TrackerConfig:
    max_hands: int = 2
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.7


class MediaPipeHandTracker:
    """Lazy MediaPipe adapter. Vendor objects do not cross this boundary."""

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()
        try:
            import mediapipe as mp
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Install the [vision] extra to use camera tracking") from exc
        self._mp = mp
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=self.config.max_hands,
            min_detection_confidence=self.config.min_detection_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
        )

    def process(self, frame: Any, timestamp_ms: int) -> list[HandObservation]:
        rgb = frame[:, :, ::-1]
        result = self._hands.process(rgb)
        observations: list[HandObservation] = []
        for index, hand_landmarks in enumerate(result.multi_hand_landmarks or []):
            label = "unknown"
            if result.multi_handedness and index < len(result.multi_handedness):
                label = result.multi_handedness[index].classification[0].label.lower()
            landmarks = tuple(
                Point3D(point.x, point.y, point.z) for point in hand_landmarks.landmark
            )
            confidence = 0.0
            if result.multi_handedness and index < len(result.multi_handedness):
                confidence = result.multi_handedness[index].classification[0].score
            observations.append(HandObservation(label, landmarks, confidence, timestamp_ms))
        return observations

    def close(self) -> None:
        self._hands.close()
