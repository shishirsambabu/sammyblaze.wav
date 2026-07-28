from __future__ import annotations

from enum import StrEnum


class PerformanceMode(StrEnum):
    """The note voices enabled by the performer-facing control surface."""

    CHORD_SCALE = "chord + scale"
    CHORD_ONLY = "chords only"
    SCALE_ONLY = "scale only"
    EFFECTS = "effects only"

    def next(self) -> PerformanceMode:
        modes = tuple(type(self))
        return modes[(modes.index(self) + 1) % len(modes)]

    @property
    def accepts_chords(self) -> bool:
        return self in (PerformanceMode.CHORD_SCALE, PerformanceMode.CHORD_ONLY)

    @property
    def accepts_scale(self) -> bool:
        return self in (PerformanceMode.CHORD_SCALE, PerformanceMode.SCALE_ONLY)
