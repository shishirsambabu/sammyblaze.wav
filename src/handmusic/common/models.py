from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Handedness = Literal["left", "right", "unknown"]


@dataclass(frozen=True, slots=True)
class Point3D:
    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True, slots=True)
class HandObservation:
    handedness: Handedness
    landmarks: tuple[Point3D, ...]
    confidence: float
    timestamp_ms: int

    def __post_init__(self) -> None:
        if len(self.landmarks) != 21:
            raise ValueError("MediaPipe hand observations must contain 21 landmarks")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class GestureFeatures:
    handedness: Handedness
    fingers_open: tuple[bool, bool, bool, bool, bool]
    pinch_distance: float
    palm_rotation_deg: float
    center_x: float
    center_y: float
    depth: float
    velocity_x: float
    velocity_y: float
    confidence: float
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class MusicalCommand:
    action: str
    value: float | int | str | None = None
    timestamp_ms: int = 0
