from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from threading import RLock
from time import monotonic
from typing import Literal

MidiEventKind = Literal["note_on", "note_off", "cc", "program"]


@dataclass(frozen=True, slots=True)
class LoopEvent:
    offset_ms: int
    kind: MidiEventKind
    data1: int
    data2: int = 0


@dataclass(frozen=True, slots=True)
class TransportSnapshot:
    recording: bool
    playing: bool
    event_count: int
    loop_length_ms: int

    def as_dict(self) -> dict[str, bool | int]:
        return asdict(self)


class LoopTransport:
    """Thread-safe live MIDI router with bounded capture and deterministic looping."""

    def __init__(
        self,
        sink: object,
        *,
        clock_ms: Callable[[], int] | None = None,
        max_events: int = 4096,
        minimum_loop_ms: int = 500,
    ) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        if minimum_loop_ms < 1:
            raise ValueError("minimum_loop_ms must be positive")
        self.sink = sink
        self.max_events = max_events
        self.minimum_loop_ms = minimum_loop_ms
        self._clock_ms = clock_ms or (lambda: round(monotonic() * 1000))
        self._lock = RLock()
        self._events: list[LoopEvent] = []
        self._recording = False
        self._recording_start_ms = 0
        self._recording_notes: set[int] = set()
        self._playing = False
        self._playback_start_ms = 0
        self._playback_cycle = 0
        self._next_event_index = 0
        self._loop_length_ms = 0
        self._live_notes: set[int] = set()
        self._live_velocities: dict[int, int] = {}
        self._loop_notes: set[int] = set()
        self._closed = False

    @property
    def events(self) -> tuple[LoopEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def snapshot(self) -> TransportSnapshot:
        with self._lock:
            return TransportSnapshot(
                recording=self._recording,
                playing=self._playing,
                event_count=len(self._events),
                loop_length_ms=self._loop_length_ms,
            )

    def note_on(self, note: int, velocity: int) -> None:
        with self._lock:
            self._ensure_open()
            if note not in self._live_notes and note not in self._loop_notes:
                self.sink.note_on(note, velocity)
            self._live_notes.add(note)
            self._live_velocities[note] = velocity
            self._record("note_on", note, velocity)

    def note_off(self, note: int) -> None:
        with self._lock:
            self._ensure_open()
            self._live_notes.discard(note)
            self._live_velocities.pop(note, None)
            if note not in self._loop_notes:
                self.sink.note_off(note)
            self._record("note_off", note, 0)

    def control_change(self, control: int, value: int) -> None:
        with self._lock:
            self._ensure_open()
            self.sink.control_change(control, value)
            self._record("cc", control, value)

    def program_change(self, program: int) -> None:
        with self._lock:
            self._ensure_open()
            self.sink.program_change(program)
            self._record("program", program, 0)

    def start_recording(self, timestamp_ms: int | None = None) -> None:
        with self._lock:
            self._ensure_open()
            now = self._now(timestamp_ms)
            self._stop_playback_locked()
            self._events.clear()
            self._loop_length_ms = 0
            self._recording = True
            self._recording_start_ms = now
            self._recording_notes = set(self._live_notes)
            for note in sorted(self._live_notes):
                self._append(LoopEvent(0, "note_on", note, self._live_velocities[note]))

    def stop_recording(self, timestamp_ms: int | None = None) -> bool:
        with self._lock:
            if not self._recording:
                return False
            now = self._now(timestamp_ms)
            length = max(self.minimum_loop_ms, now - self._recording_start_ms)
            for note in sorted(self._recording_notes):
                self._append(LoopEvent(length, "note_off", note))
            self._recording_notes.clear()
            self._recording = False
            self._loop_length_ms = length
            return bool(self._events)

    def start_playback(self, timestamp_ms: int | None = None) -> bool:
        with self._lock:
            self._ensure_open()
            if self._recording or not self._events or self._loop_length_ms <= 0:
                return False
            self._stop_playback_locked()
            self._playing = True
            self._playback_start_ms = self._now(timestamp_ms)
            self._playback_cycle = 0
            self._next_event_index = 0
            return True

    def stop_playback(self) -> None:
        with self._lock:
            self._stop_playback_locked()

    def clear(self) -> None:
        with self._lock:
            self._recording = False
            self._recording_notes.clear()
            self._stop_playback_locked()
            self._events.clear()
            self._loop_length_ms = 0

    def tick(self, timestamp_ms: int | None = None) -> int:
        with self._lock:
            if not self._playing:
                return 0
            now = self._now(timestamp_ms)
            elapsed = max(0, now - self._playback_start_ms)
            target_cycle = elapsed // self._loop_length_ms
            cycle_position = elapsed % self._loop_length_ms
            emitted = 0

            if target_cycle - self._playback_cycle > 1:
                self._release_loop_notes()
                self._playback_cycle = target_cycle
                self._next_event_index = 0

            while self._playback_cycle < target_cycle:
                emitted += self._emit_through(self._loop_length_ms)
                self._playback_cycle += 1
                self._next_event_index = 0
            emitted += self._emit_through(cycle_position)
            return emitted

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._recording = False
            self._stop_playback_locked()
            for note in tuple(self._live_notes):
                self.sink.note_off(note)
            self._live_notes.clear()
            self._live_velocities.clear()
            close = getattr(self.sink, "close", None)
            if close is not None:
                close()
            self._closed = True

    def _record(self, kind: MidiEventKind, data1: int, data2: int) -> None:
        if not self._recording:
            return
        offset = max(0, self._clock_ms() - self._recording_start_ms)
        self._append(LoopEvent(offset, kind, data1, data2))
        if kind == "note_on":
            self._recording_notes.add(data1)
        elif kind == "note_off":
            self._recording_notes.discard(data1)

    def _append(self, event: LoopEvent) -> None:
        if len(self._events) < self.max_events:
            self._events.append(event)

    def _emit_through(self, offset_ms: int) -> int:
        emitted = 0
        while (
            self._next_event_index < len(self._events)
            and self._events[self._next_event_index].offset_ms <= offset_ms
        ):
            self._emit(self._events[self._next_event_index])
            self._next_event_index += 1
            emitted += 1
        return emitted

    def _emit(self, event: LoopEvent) -> None:
        if event.kind == "note_on":
            if event.data1 not in self._live_notes and event.data1 not in self._loop_notes:
                self.sink.note_on(event.data1, event.data2)
            self._loop_notes.add(event.data1)
        elif event.kind == "note_off":
            self._loop_notes.discard(event.data1)
            if event.data1 not in self._live_notes:
                self.sink.note_off(event.data1)
        elif event.kind == "cc":
            self.sink.control_change(event.data1, event.data2)
        else:
            self.sink.program_change(event.data1)

    def _stop_playback_locked(self) -> None:
        self._playing = False
        self._playback_cycle = 0
        self._next_event_index = 0
        self._release_loop_notes()

    def _release_loop_notes(self) -> None:
        for note in tuple(self._loop_notes):
            if note not in self._live_notes:
                self.sink.note_off(note)
        self._loop_notes.clear()

    def _now(self, timestamp_ms: int | None) -> int:
        return self._clock_ms() if timestamp_ms is None else timestamp_ms

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("loop transport is closed")
