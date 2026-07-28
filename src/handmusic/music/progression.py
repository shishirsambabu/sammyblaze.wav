from __future__ import annotations

from dataclasses import dataclass

from .chord_engine import ChordSpec, chord_notes


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
