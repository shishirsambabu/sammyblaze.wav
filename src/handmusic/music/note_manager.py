from __future__ import annotations

from typing import Protocol


class NoteSink(Protocol):
    def note_on(self, note: int, velocity: int) -> None: ...
    def note_off(self, note: int) -> None: ...
    def control_change(self, control: int, value: int) -> None: ...
    def program_change(self, program: int) -> None: ...


def _midi(value: int) -> int:
    if not 0 <= value <= 127:
        raise ValueError("MIDI value must be between 0 and 127")
    return value


class NoteManager:
    """Single owner of active-note truth and emergency cleanup."""

    def __init__(self, sink: NoteSink) -> None:
        self.sink = sink
        self.active_notes: set[int] = set()
        self.sustain_enabled = False
        self._owners: dict[int, set[str]] = {}
        self._closed = False

    def play_chord(self, notes: tuple[int, ...], velocity: int = 96) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        velocity = _midi(velocity)
        self._release_owner("chord")
        for note in notes:
            note = _midi(note)
            self._acquire(note, "chord", velocity)

    def stop_chord(self) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        self._release_owner("chord")

    def play_melody_note(
        self,
        note: int,
        velocity: int = 96,
        *,
        legato: bool = True,
        retrigger: bool = False,
    ) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        note = _midi(note)
        velocity = _midi(velocity)
        if "melody" in self._owners.get(note, set()):
            if not retrigger:
                return
            if "chord" in self._owners[note]:
                self.sink.note_on(note, velocity)
                return
            self._release_owner("melody")
            self._acquire(note, "melody", velocity)
            return
        if legato:
            self._acquire(note, "melody", velocity)
            self._release_owner("melody", except_note=note)
        else:
            self._release_owner("melody")
            self._acquire(note, "melody", velocity)

    def stop_melody_note(self) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        self._release_owner("melody")

    def set_sustain(self, enabled: bool) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        enabled = bool(enabled)
        if enabled == self.sustain_enabled:
            return
        self.sustain_enabled = enabled
        self.sink.control_change(64, 127 if enabled else 0)

    def control_change(self, control: int, value: int) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        self.sink.control_change(_midi(control), _midi(value))

    def program_change(self, program: int) -> None:
        if self._closed:
            raise RuntimeError("note manager is closed")
        self.sink.program_change(_midi(program))

    def stop_all(self) -> None:
        for note in tuple(self.active_notes):
            self.sink.note_off(note)
        self._owners.clear()
        self.active_notes.clear()
        if self.sustain_enabled:
            self.sustain_enabled = False
            self.sink.control_change(64, 0)

    def close(self) -> None:
        if self._closed:
            return
        self.stop_all()
        self._closed = True
        close = getattr(self.sink, "close", None)
        if close is not None:
            close()

    def _acquire(self, note: int, owner: str, velocity: int) -> None:
        owners = self._owners.setdefault(note, set())
        if not owners:
            self.sink.note_on(note, velocity)
        owners.add(owner)
        self.active_notes.add(note)

    def _release_owner(self, owner: str, except_note: int | None = None) -> None:
        for note, owners in tuple(self._owners.items()):
            if owner not in owners or note == except_note:
                continue
            owners.remove(owner)
            if not owners:
                self.sink.note_off(note)
                self.active_notes.discard(note)
                del self._owners[note]
