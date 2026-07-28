from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import Handedness


class GestureKind(StrEnum):
    NO_GESTURE = "no_gesture"
    ARM = "arm"
    STOP_ALL = "stop_all"
    NEXT_CHORD = "next_chord"
    PREVIOUS_CHORD = "previous_chord"
    TOGGLE_ARPEGGIATOR = "toggle_arpeggiator"


@dataclass(frozen=True, slots=True)
class GestureEvent:
    kind: GestureKind
    handedness: Handedness
    confidence: float
    timestamp_ms: int
