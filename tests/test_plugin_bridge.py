from __future__ import annotations

import struct

import pytest

from handmusic.music.midi_output import bridge_packet


def test_bridge_packet_is_fixed_versioned_and_little_endian() -> None:
    packet = bridge_packet(3, 74, 101, channel=2, sequence=0x12345678)

    assert len(packet) == 14
    assert struct.unpack("<4sBBBBBBI", packet) == (
        b"SBW1",
        1,
        3,
        2,
        74,
        101,
        0,
        0x12345678,
    )


def test_bridge_packet_rejects_invalid_midi_values() -> None:
    with pytest.raises(ValueError):
        bridge_packet(1, 128, 100)


def test_bridge_packet_supports_sound_program_changes() -> None:
    packet = bridge_packet(5, 111, sequence=9)

    assert struct.unpack("<4sBBBBBBI", packet)[1:] == (1, 5, 0, 111, 0, 0, 9)


def test_bridge_packet_supports_live_sound_parameter_changes() -> None:
    packet = bridge_packet(6, 18, 92, sequence=10)

    assert struct.unpack("<4sBBBBBBI", packet)[1:] == (1, 6, 0, 18, 92, 0, 10)
