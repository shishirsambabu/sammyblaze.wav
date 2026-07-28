from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MemoryMidiOutput:
    """Deterministic sink for dry-runs, tests, and diagnostics."""

    messages: list[tuple[str, int, int | None]] = field(default_factory=list)

    def note_on(self, note: int, velocity: int) -> None:
        self.messages.append(("note_on", note, velocity))

    def note_off(self, note: int) -> None:
        self.messages.append(("note_off", note, None))

    def control_change(self, control: int, value: int) -> None:
        self.messages.append(("cc", control, value))


class MidoOutput:
    """Optional real MIDI adapter. Importing this module does not require Mido."""

    def __init__(self, port_name: str | None = None) -> None:
        try:
            import mido
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("Install the [midi] extra to use MIDI output") from exc
        self._mido = mido
        self._port = mido.open_output(port_name)

    def note_on(self, note: int, velocity: int) -> None:
        self._port.send(self._mido.Message("note_on", note=note, velocity=velocity))

    def note_off(self, note: int) -> None:
        self._port.send(self._mido.Message("note_off", note=note, velocity=0))

    def control_change(self, control: int, value: int) -> None:
        self._port.send(self._mido.Message("control_change", control=control, value=value))

    def close(self) -> None:
        self._port.close()
