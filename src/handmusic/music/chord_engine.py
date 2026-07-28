from __future__ import annotations

from dataclasses import dataclass

ROOTS = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}
QUALITIES: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
    "augmented": (0, 4, 8),
    "dominant7": (0, 4, 7, 10),
    "major7": (0, 4, 7, 11),
    "minor7": (0, 3, 7, 10),
}


@dataclass(frozen=True, slots=True)
class ChordSpec:
    root: str
    quality: str = "major"
    inversion: int = 0
    octave: int = 4
    open_voicing: bool = False


def chord_notes(spec: ChordSpec) -> tuple[int, ...]:
    if spec.root not in ROOTS:
        raise ValueError(f"unsupported root: {spec.root}")
    if spec.quality not in QUALITIES:
        raise ValueError(f"unsupported quality: {spec.quality}")
    intervals = QUALITIES[spec.quality]
    if not 0 <= spec.inversion < len(intervals):
        raise ValueError(f"inversion must be between 0 and {len(intervals) - 1}")
    if not 0 <= spec.octave <= 8:
        raise ValueError("octave must be between 0 and 8")
    notes = [12 * (spec.octave + 1) + ROOTS[spec.root] + interval for interval in intervals]
    for index in range(spec.inversion):
        notes[index] += 12
    notes = sorted(notes[spec.inversion :] + notes[: spec.inversion])
    if spec.open_voicing and len(notes) >= 3:
        notes[1] += 12
        notes = sorted(notes)
    return tuple(notes)
