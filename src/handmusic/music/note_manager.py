from __future__ import annotations

from typing import Protocol


class NoteSink(Protocol):
    def note_on(self, note: int, velocity: int) -> None: ...
    def note_off(self, note: int) -> None: ...
    def control_change(self, control: int, value: int) -> None: ...


def _midi(value: int) -> int:
    if not 0 <= value <= 127:
        raise ValueError("MIDI value must be between 0 and 127")
    return value


class NoteManager:
    """Single owner of active-note truth and emergency cleanup."""

    def __init__(self, sink: NoteSink) -> None:
        self.sink = sink
        self.active_notes: set[int] = set()
        self._closed = False

    def play_chord(self, notes: tuple[int, ...], velocity: int = 96) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        velocity = _midi(velocity)
        self.stop_all()
        for note in notes:
            note = _midi(note)
            self.sink.note_on(note, velocity)
            self.active_notes.add(note)

    def control_change(self, control: int, value: int) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        self.sink.control_change(_midi(control), _midi(value))

    def stop_all(self) -> None:
        for note in tuple(self.active_notes):
            self.sink.note_off(note)
        self.active_notes.clear()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.stop_all()
        close = getattr(self.sink, "close", None)
        if close is not None:
            close()
