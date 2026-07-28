from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from handmusic.common.models import HandObservation, Point3D


@dataclass(frozen=True, slots=True)
class TrackerConfig:
    max_hands: int = 2
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.7
    model_path: str = "models/hand_landmarker.task"


def hand_model_candidates(model_path: str | Path) -> tuple[Path, ...]:
    """Return model locations for source, editable, and PyInstaller launches."""

    requested = Path(model_path).expanduser()
    if requested.is_absolute():
        return (requested,)
    roots: list[Path] = [Path.cwd()]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    roots.append(Path(__file__).resolve().parents[3])
    roots.append(Path(sys.executable).resolve().parent)
    candidates: list[Path] = []
    for root in roots:
        candidate = root / requested
        if candidate not in candidates:
            candidates.append(candidate)
    return tuple(candidates)


def resolve_hand_model_path(model_path: str | Path) -> Path:
    """Resolve a hand model without requiring the process to start in repo root."""

    candidates = hand_model_candidates(model_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return candidates[0]


class MediaPipeHandTracker:
    """Lazy MediaPipe adapter. Vendor objects do not cross this boundary."""

    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.config = config or TrackerConfig()
        try:
            import mediapipe as mp
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Install the [vision] extra to use camera tracking") from exc
        self._mp = mp
        if hasattr(mp, "solutions"):
            self._mode = "legacy"
            self._hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=self.config.max_hands,
                min_detection_confidence=self.config.min_detection_confidence,
                min_tracking_confidence=self.config.min_tracking_confidence,
            )
        else:
            model_path = resolve_hand_model_path(self.config.model_path)
            if not model_path.is_file():
                checked = ", ".join(
                    str(path) for path in hand_model_candidates(self.config.model_path)
                )
                raise RuntimeError(
                    "MediaPipe Tasks API requires a hand_landmarker.task model. "
                    f"Checked: {checked}. Download it or pass --hand-model with an absolute path."
                )
            self._mode = "tasks"
            base_options = mp.tasks.BaseOptions(model_asset_path=str(model_path))
            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=self.config.max_hands,
                min_hand_detection_confidence=self.config.min_detection_confidence,
                min_hand_presence_confidence=self.config.min_tracking_confidence,
                min_tracking_confidence=self.config.min_tracking_confidence,
            )
            try:
                self._hands = mp.tasks.vision.HandLandmarker.create_from_options(options)
            except OSError as exc:  # pragma: no cover - depends on host policy
                raise RuntimeError(
                    "Windows blocked MediaPipe's native runtime. Allow the mediapipe "
                    "shared library in App Control or run on a supported Python environment."
                ) from exc

    def process(self, frame: Any, timestamp_ms: int) -> list[HandObservation]:
        rgb = frame[:, :, ::-1].copy()
        if self._mode == "legacy":
            result = self._hands.process(rgb)
            handedness_results = [item.classification for item in (result.multi_handedness or [])]
            landmark_results = result.multi_hand_landmarks or []
        else:
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            result = self._hands.detect_for_video(image, timestamp_ms)
            handedness_results = result.handedness or []
            landmark_results = result.hand_landmarks or []
        observations: list[HandObservation] = []
        for index, hand_landmarks in enumerate(landmark_results):
            label = "unknown"
            if index < len(handedness_results):
                category = handedness_results[index][0]
                label = (category.category_name or "unknown").lower()
            points = hand_landmarks.landmark if self._mode == "legacy" else hand_landmarks
            landmarks = tuple(Point3D(point.x, point.y, point.z) for point in points)
            confidence = 0.0
            if index < len(handedness_results):
                confidence = handedness_results[index][0].score
            observations.append(HandObservation(label, landmarks, confidence, timestamp_ms))
        return observations

    def close(self) -> None:
        self._hands.close()
