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
