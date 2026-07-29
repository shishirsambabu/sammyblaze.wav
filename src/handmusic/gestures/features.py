from __future__ import annotations

import math

from handmusic.common.models import GestureFeatures, HandObservation, Point3D

WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_TIP = 20


def _distance(a: Point3D, b: Point3D) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _finger_open(landmarks: tuple[Point3D, ...], mcp: int, pip: int, tip: int) -> bool:
    # Image coordinates grow downward. The simple rule is intentionally replaceable
    # by a calibrated angle model once real performer data is available.
    return landmarks[tip].y < landmarks[pip].y < landmarks[mcp].y


def extract_features(
    observation: HandObservation,
    previous: GestureFeatures | None = None,
    dt_ms: int | None = None,
) -> GestureFeatures:
    lm = observation.landmarks
    palm_size = max(_distance(lm[WRIST], lm[MIDDLE_MCP]), 1e-6)
    center_x = sum(point.x for point in lm[0:21]) / 21
    center_y = sum(point.y for point in lm[0:21]) / 21
    dt = max((dt_ms or (observation.timestamp_ms - previous.timestamp_ms if previous else 1)), 1)
    velocity_x = 0.0
    velocity_y = 0.0
    if previous:
        velocity_x = (center_x - previous.center_x) / (dt / 1000.0)
        velocity_y = (center_y - previous.center_y) / (dt / 1000.0)
    palm_angle = math.degrees(
        math.atan2(lm[INDEX_MCP].y - lm[WRIST].y, lm[INDEX_MCP].x - lm[WRIST].x)
    )
    fingers = (
        _finger_open(lm, INDEX_MCP, INDEX_PIP, INDEX_TIP),
        _finger_open(lm, MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP),
        _finger_open(lm, RING_MCP, RING_PIP, RING_TIP),
        _finger_open(lm, PINKY_MCP, PINKY_PIP, PINKY_TIP),
        _distance(lm[THUMB_TIP], lm[INDEX_MCP]) > palm_size * 0.8,
    )
    return GestureFeatures(
        handedness=observation.handedness,
        fingers_open=fingers,
        pinch_distance=_distance(lm[THUMB_TIP], lm[INDEX_TIP]) / palm_size,
        palm_rotation_deg=palm_angle,
        center_x=center_x,
        center_y=center_y,
        depth=sum(point.z for point in lm) / 21,
        velocity_x=velocity_x,
        velocity_y=velocity_y,
        confidence=observation.confidence,
        timestamp_ms=observation.timestamp_ms,
    )
