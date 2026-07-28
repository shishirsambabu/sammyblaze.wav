from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field

PLUGIN_BRIDGE_HOST = "127.0.0.1"
PLUGIN_BRIDGE_PORT = 18736
_BRIDGE_PACKET = struct.Struct("<4sBBBBBBI")
_BRIDGE_MAGIC = b"SBW1"
_BRIDGE_VERSION = 1
_NOTE_ON = 1
_NOTE_OFF = 2
_CONTROL_CHANGE = 3
_PANIC = 4


def bridge_packet(
    message_type: int,
    data1: int = 0,
    data2: int = 0,
    *,
    channel: int = 0,
    sequence: int = 0,
) -> bytes:
    """Encode the fixed-size, versioned localhost bridge packet."""

    values = (message_type, channel, data1, data2)
    if any(not 0 <= value <= 127 for value in values):
        raise ValueError("bridge MIDI values must be between 0 and 127")
    return _BRIDGE_PACKET.pack(
        _BRIDGE_MAGIC,
        _BRIDGE_VERSION,
        message_type,
        channel,
        data1,
        data2,
        0,
        sequence & 0xFFFFFFFF,
    )


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
        try:
            self._port = mido.open_output(port_name)
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "MIDI backend unavailable. Install the [midi-native] extra with a C++ "
                "build toolchain "
                "or run camera diagnostics with --output null."
            ) from exc

    def note_on(self, note: int, velocity: int) -> None:
        self._port.send(self._mido.Message("note_on", note=note, velocity=velocity))

    def note_off(self, note: int) -> None:
        self._port.send(self._mido.Message("note_off", note=note, velocity=0))

    def control_change(self, control: int, value: int) -> None:
        self._port.send(self._mido.Message("control_change", control=control, value=value))

    def close(self) -> None:
        self._port.close()


class PluginBridgeOutput:
    """Low-latency localhost transport for the native VST3 gesture receiver."""

    def __init__(
        self,
        host: str = PLUGIN_BRIDGE_HOST,
        port: int = PLUGIN_BRIDGE_PORT,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("plugin bridge port must be between 1 and 65535")
        self._address = (host, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sequence = 0
        self._closed = False

    def note_on(self, note: int, velocity: int) -> None:
        self._send(_NOTE_ON, note, velocity)

    def note_off(self, note: int) -> None:
        self._send(_NOTE_OFF, note, 0)

    def control_change(self, control: int, value: int) -> None:
        self._send(_CONTROL_CHANGE, control, value)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._send(_PANIC, 0, 0)
        finally:
            self._closed = True
            self._socket.close()

    def _send(self, message_type: int, data1: int, data2: int) -> None:
        if self._closed:
            return
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        packet = bridge_packet(
            message_type,
            data1,
            data2,
            sequence=self._sequence,
        )
        self._socket.sendto(packet, self._address)
