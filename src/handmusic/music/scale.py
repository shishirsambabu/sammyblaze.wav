from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScaleSpec:
    name: str
    intervals: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("scale name cannot be empty")
        if not self.intervals or self.intervals[0] != 0:
            raise ValueError("scale intervals must start at zero")
        if any(
            left >= right
            for left, right in zip(self.intervals, self.intervals[1:], strict=False)
        ):
            raise ValueError("scale intervals must be strictly increasing")


SCALES: dict[str, ScaleSpec] = {
    "major": ScaleSpec("Major", (0, 2, 4, 5, 7, 9, 11, 12)),
    "minor": ScaleSpec("Natural minor", (0, 2, 3, 5, 7, 8, 10, 12)),
    "major_pentatonic": ScaleSpec("Major pentatonic", (0, 2, 4, 7, 9, 12)),
    "minor_pentatonic": ScaleSpec("Minor pentatonic", (0, 3, 5, 7, 10, 12)),
    "dorian": ScaleSpec("Dorian", (0, 2, 3, 5, 7, 9, 10, 12)),
    "blues": ScaleSpec("Blues", (0, 3, 5, 6, 7, 10, 12)),
}


def scale_names() -> tuple[str, ...]:
    return tuple(SCALES)


def scale_for(name: str) -> ScaleSpec:
    try:
        return SCALES[name]
    except KeyError as exc:
        choices = ", ".join(scale_names())
        raise ValueError(f"unknown scale {name!r}; choose one of: {choices}") from exc


@dataclass(slots=True)
class ScaleEngine:
    """Map a normalized right-hand position to a bounded scale note."""

    spec: ScaleSpec = SCALES["major"]
    root_midi: int = 60
    octaves: int = 2

    def __post_init__(self) -> None:
        if not 0 <= self.root_midi <= 127:
            raise ValueError("root_midi must be between 0 and 127")
        if self.octaves < 1:
            raise ValueError("octaves must be positive")

    @property
    def notes(self) -> tuple[int, ...]:
        values = (
            self.root_midi + octave * 12 + interval
            for octave in range(self.octaves)
            for interval in self.spec.intervals
        )
        return tuple(dict.fromkeys(note for note in values if note <= 127))

    def note_for_position(self, center_x: float) -> int:
        notes = self.notes
        normalized = max(0.0, min(1.0, center_x))
        index = round(normalized * (len(notes) - 1))
        return notes[index]
