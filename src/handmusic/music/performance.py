from __future__ import annotations

from dataclasses import dataclass, field

from handmusic.common.models import GestureFeatures

from .scale import ScaleEngine

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def midi_note_name(note: int) -> str:
    if not 0 <= note <= 127:
        raise ValueError("MIDI note must be between 0 and 127")
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


@dataclass(slots=True)
class VoiceLeadingEngine:
    """Choose compact left-hand inversions with minimal inter-chord movement."""

    low_note: int = 43
    high_note: int = 67
    target_center: float = 55.0
    previous: tuple[int, ...] = field(default=(), init=False)

    def voice(self, notes: tuple[int, ...]) -> tuple[int, ...]:
        if not notes:
            raise ValueError("at least one chord note is required")
        base = tuple(sorted(notes))
        root_pitch_class = base[0] % 12
        candidates: set[tuple[int, ...]] = set()
        for inversion in range(len(base)):
            inverted = base[inversion:] + tuple(note + 12 for note in base[:inversion])
            for shift in range(-48, 49, 12):
                candidate = tuple(note + shift for note in inverted)
                if self.low_note <= candidate[0] and candidate[-1] <= self.high_note:
                    candidates.add(candidate)
        if not candidates:
            raise ValueError("no playable chord voicing fits the configured register")

        def score(candidate: tuple[int, ...]) -> tuple[float, float, tuple[int, ...]]:
            center = sum(candidate) / len(candidate)
            center_cost = abs(center - self.target_center)
            if self.previous and len(self.previous) == len(candidate):
                movement = sum(
                    abs(current - prior)
                    for current, prior in zip(candidate, self.previous, strict=True)
                )
                root_cost = 0.0
            else:
                movement = 0.0
                root_cost = 3.0 if candidate[0] % 12 != root_pitch_class else 0.0
            return movement + center_cost * 0.1 + root_cost, center_cost, candidate

        selected = min(candidates, key=score)
        self.previous = selected
        return selected

    def reset(self) -> None:
        self.previous = ()


@dataclass(frozen=True, slots=True)
class MelodyDecision:
    note: int
    velocity: int
    retrigger: bool = False


@dataclass(slots=True)
class MelodyPerformanceEngine:
    """Turn right-hand motion into stable, expressive, scale-locked melody notes."""

    scale: ScaleEngine
    hysteresis: float = 0.018
    pinch_threshold: float = 0.42
    _index: int | None = field(default=None, init=False)
    _pinch_active: bool = field(default=False, init=False)

    def perform(self, features: GestureFeatures) -> MelodyDecision:
        notes = self.scale.notes
        normalized = max(0.0, min(1.0, features.center_x))
        target = round(normalized * (len(notes) - 1))
        if self._index is None:
            self._index = target
        else:
            spacing = 1.0 / max(len(notes) - 1, 1)
            lower = (self._index - 0.5) * spacing - self.hysteresis
            upper = (self._index + 0.5) * spacing + self.hysteresis
            if normalized < lower or normalized > upper:
                self._index = target

        pinch_active = features.pinch_distance <= self.pinch_threshold
        retrigger = pinch_active and not self._pinch_active
        self._pinch_active = pinch_active
        height = max(0.0, min(1.0, 1.0 - features.center_y))
        strike = max(0.0, min(1.0, features.velocity_y / 1.5))
        velocity = round(52 + height * 50 + strike * 25)
        velocity = max(45, min(127, velocity))
        return MelodyDecision(notes[self._index], velocity, retrigger)

    def reset(self) -> None:
        self._index = None
        self._pinch_active = False
