from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from handmusic.common.models import GestureFeatures

from .chord_engine import QUALITIES, ROOTS, ChordSpec
from .scale import ScaleEngine

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def midi_note_name(note: int) -> str:
    if not 0 <= note <= 127:
        raise ValueError("MIDI note must be between 0 and 127")
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


class ScaleNoteSource(Protocol):
    @property
    def notes(self) -> tuple[int, ...]: ...


class LeadScaleMode(StrEnum):
    ADAPTIVE = "adaptive"
    COLOR = "color"
    PENTATONIC = "pentatonic"
    BLUES = "blues"
    CHORD_TONES = "chord tones"


SCALE_INTERVALS: dict[str, tuple[int, ...]] = {
    "Ionian": (0, 2, 4, 5, 7, 9, 11, 12),
    "Lydian": (0, 2, 4, 6, 7, 9, 11, 12),
    "Aeolian": (0, 2, 3, 5, 7, 8, 10, 12),
    "Dorian": (0, 2, 3, 5, 7, 9, 10, 12),
    "Mixolydian": (0, 2, 4, 5, 7, 9, 10, 12),
    "Altered": (0, 1, 3, 4, 6, 8, 10, 12),
    "Locrian": (0, 1, 3, 5, 6, 8, 10, 12),
    "Locrian natural 2": (0, 2, 3, 5, 6, 8, 10, 12),
    "Diminished": (0, 2, 3, 5, 6, 8, 9, 11, 12),
    "Whole tone": (0, 2, 4, 6, 8, 10, 12),
    "Lydian augmented": (0, 2, 4, 6, 8, 9, 11, 12),
    "Major pentatonic": (0, 2, 4, 7, 9, 12),
    "Minor pentatonic": (0, 3, 5, 7, 10, 12),
    "Blues": (0, 3, 5, 6, 7, 10, 12),
}


def lead_mode_for_scale_name(name: str) -> LeadScaleMode:
    if "pentatonic" in name:
        return LeadScaleMode.PENTATONIC
    if name == "blues":
        return LeadScaleMode.BLUES
    if name == "dorian":
        return LeadScaleMode.COLOR
    return LeadScaleMode.ADAPTIVE


@dataclass(slots=True)
class HarmonicScaleEngine:
    """Build a chord-relative lead scale for the active left-hand harmony."""

    chord: ChordSpec
    mode: LeadScaleMode = LeadScaleMode.ADAPTIVE
    root_octave: int = 4
    octaves: int = 2

    def set_chord(self, chord: ChordSpec) -> None:
        self.chord = chord

    def cycle_mode(self) -> LeadScaleMode:
        modes = tuple(LeadScaleMode)
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        return self.mode

    @property
    def scale_name(self) -> str:
        return self._scale_definition()[0]

    @property
    def label(self) -> str:
        return f"{self.chord.root} {self.scale_name}"

    @property
    def notes(self) -> tuple[int, ...]:
        _, intervals = self._scale_definition()
        root = 12 * (self.root_octave + 1) + ROOTS[self.chord.root]
        values = (
            root + octave * 12 + interval
            for octave in range(self.octaves)
            for interval in intervals
        )
        return tuple(dict.fromkeys(note for note in values if note <= 127))

    def _scale_definition(self) -> tuple[str, tuple[int, ...]]:
        quality = self.chord.quality
        minor = quality in {"minor", "minor7", "diminished", "half_diminished"}
        if self.mode is LeadScaleMode.CHORD_TONES:
            return "Chord tones", (*QUALITIES[quality], 12)
        if self.mode is LeadScaleMode.PENTATONIC:
            name = "Minor pentatonic" if minor else "Major pentatonic"
        elif self.mode is LeadScaleMode.BLUES:
            name = "Blues"
        elif self.mode is LeadScaleMode.COLOR:
            name = {
                "major": "Lydian",
                "major7": "Lydian",
                "minor": "Dorian",
                "minor7": "Dorian",
                "dominant7": "Altered",
                "diminished": "Diminished",
                "half_diminished": "Locrian natural 2",
                "augmented": "Lydian augmented",
            }[quality]
        else:
            name = {
                "major": "Ionian",
                "major7": "Ionian",
                "minor": "Aeolian",
                "minor7": "Aeolian",
                "dominant7": "Mixolydian",
                "diminished": "Locrian",
                "half_diminished": "Locrian",
                "augmented": "Whole tone",
            }[quality]
        intervals = tuple(
            sorted(set(SCALE_INTERVALS[name]) | set(QUALITIES[quality]) | {12})
        )
        return name, intervals


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

    scale: ScaleNoteSource | ScaleEngine
    hysteresis: float = 0.018
    pinch_threshold: float = 0.42
    _index: int | None = field(default=None, init=False)
    _pinch_active: bool = field(default=False, init=False)
    _position: float | None = field(default=None, init=False)

    def perform(self, features: GestureFeatures) -> MelodyDecision:
        notes = self.scale.notes
        normalized = max(0.0, min(1.0, features.center_x))
        self._position = normalized
        target = round(normalized * (len(notes) - 1))
        if self._index is None or self._index >= len(notes):
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

    def retuned_note(self) -> int | None:
        if self._position is None:
            return None
        notes = self.scale.notes
        self._index = round(self._position * (len(notes) - 1))
        return notes[self._index]

    def reset(self) -> None:
        self._index = None
        self._pinch_active = False
        self._position = None
