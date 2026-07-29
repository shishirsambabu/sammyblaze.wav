from __future__ import annotations

from dataclasses import dataclass

from .chord_engine import ChordSpec, chord_notes

PROGRESSIONS: dict[str, tuple[ChordSpec, ...]] = {
    "pop": (
        ChordSpec("C", "major"),
        ChordSpec("A", "minor"),
        ChordSpec("F", "major"),
        ChordSpec("G", "major"),
    ),
    "anthem": (
        ChordSpec("C", "major"),
        ChordSpec("G", "major"),
        ChordSpec("A", "minor"),
        ChordSpec("F", "major"),
    ),
    "minor_drive": (
        ChordSpec("A", "minor"),
        ChordSpec("F", "major"),
        ChordSpec("C", "major"),
        ChordSpec("G", "major"),
    ),
    "jazz_ii_v_i": (
        ChordSpec("D", "minor7"),
        ChordSpec("G", "dominant7"),
        ChordSpec("C", "major7"),
    ),
    "blues": (
        ChordSpec("C", "dominant7"),
        ChordSpec("F", "dominant7"),
        ChordSpec("C", "dominant7"),
        ChordSpec("G", "dominant7"),
        ChordSpec("F", "dominant7"),
        ChordSpec("C", "dominant7"),
    ),
    "cinematic": (
        ChordSpec("C", "major", open_voicing=True),
        ChordSpec("E", "minor", open_voicing=True),
        ChordSpec("A", "minor", open_voicing=True),
        ChordSpec("F", "major", open_voicing=True),
        ChordSpec("C", "major", open_voicing=True),
        ChordSpec("G", "major", open_voicing=True),
    ),
    "neo_soul": (
        ChordSpec("C", "major7", inversion=1),
        ChordSpec("A", "minor7", inversion=1),
        ChordSpec("D", "minor7", inversion=1),
        ChordSpec("G", "dominant7", inversion=1),
    ),
}

POSE_CHORD_BANKS: dict[str, tuple[ChordSpec, ...]] = {
    "pop": (
        ChordSpec("C", "major7"),
        ChordSpec("D", "minor7"),
        ChordSpec("E", "minor7"),
        ChordSpec("F", "major7"),
        ChordSpec("G", "dominant7"),
        ChordSpec("A", "minor7"),
        ChordSpec("B", "half_diminished"),
    ),
    "anthem": (
        ChordSpec("C", "major"),
        ChordSpec("D", "minor"),
        ChordSpec("E", "minor"),
        ChordSpec("F", "major"),
        ChordSpec("G", "major"),
        ChordSpec("A", "minor"),
        ChordSpec("B", "diminished"),
    ),
    "minor_drive": (
        ChordSpec("A", "minor7"),
        ChordSpec("B", "half_diminished"),
        ChordSpec("C", "major7"),
        ChordSpec("D", "minor7"),
        ChordSpec("E", "minor7"),
        ChordSpec("F", "major7"),
        ChordSpec("G", "dominant7"),
    ),
    "jazz_ii_v_i": (
        ChordSpec("C", "major7"),
        ChordSpec("D", "minor7"),
        ChordSpec("E", "minor7"),
        ChordSpec("F", "major7"),
        ChordSpec("G", "dominant7"),
        ChordSpec("A", "minor7"),
        ChordSpec("B", "half_diminished"),
    ),
    "blues": (
        ChordSpec("C", "dominant7"),
        ChordSpec("Eb", "dominant7"),
        ChordSpec("F", "dominant7"),
        ChordSpec("Gb", "dominant7"),
        ChordSpec("G", "dominant7"),
        ChordSpec("Bb", "dominant7"),
        ChordSpec("B", "diminished"),
    ),
    "cinematic": (
        ChordSpec("C", "minor", open_voicing=True),
        ChordSpec("D", "half_diminished", open_voicing=True),
        ChordSpec("Eb", "major", open_voicing=True),
        ChordSpec("F", "minor", open_voicing=True),
        ChordSpec("G", "minor", open_voicing=True),
        ChordSpec("Ab", "major", open_voicing=True),
        ChordSpec("Bb", "major", open_voicing=True),
    ),
    "neo_soul": (
        ChordSpec("C", "major7"),
        ChordSpec("D", "minor7"),
        ChordSpec("E", "minor7"),
        ChordSpec("F", "major7"),
        ChordSpec("G", "dominant7"),
        ChordSpec("A", "minor7"),
        ChordSpec("B", "half_diminished"),
    ),
}


def progression_names() -> tuple[str, ...]:
    return tuple(PROGRESSIONS)


def progression_for(name: str) -> Progression:
    try:
        chords = PROGRESSIONS[name]
    except KeyError as exc:
        choices = ", ".join(progression_names())
        raise ValueError(f"unknown progression {name!r}; choose one of: {choices}") from exc
    return Progression(list(chords))


def pose_chords_for(name: str) -> tuple[ChordSpec, ...]:
    try:
        return POSE_CHORD_BANKS[name]
    except KeyError as exc:
        choices = ", ".join(POSE_CHORD_BANKS)
        raise ValueError(f"unknown chord bank {name!r}; choose one of: {choices}") from exc


@dataclass(slots=True)
class Progression:
    chords: list[ChordSpec]
    index: int = 0

    def __post_init__(self) -> None:
        if not self.chords:
            raise ValueError("progression cannot be empty")
        self.index %= len(self.chords)

    @property
    def current(self) -> ChordSpec:
        return self.chords[self.index]

    @property
    def current_notes(self) -> tuple[int, ...]:
        return chord_notes(self.current)

    def next(self) -> ChordSpec:
        self.index = (self.index + 1) % len(self.chords)
        return self.current

    def previous(self) -> ChordSpec:
        self.index = (self.index - 1) % len(self.chords)
        return self.current
