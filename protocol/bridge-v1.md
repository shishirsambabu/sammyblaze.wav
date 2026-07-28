# SammyBlaze bridge protocol v1

Transport: UDP/IPv4, loopback only, destination `127.0.0.1:18736`.

All packets are exactly 14 bytes:

| Offset | Size | Field | Value |
|---:|---:|---|---|
| 0 | 4 | magic | ASCII `SBW1` |
| 4 | 1 | version | `1` |
| 5 | 1 | type | `1` note-on, `2` note-off, `3` CC, `4` panic |
| 6 | 1 | channel | MIDI channel `0..127` (v1 sends `0`) |
| 7 | 1 | data1 | note or controller `0..127` |
| 8 | 1 | data2 | velocity or controller value `0..127` |
| 9 | 1 | flags | reserved, must be `0` |
| 10 | 4 | sequence | unsigned little-endian sequence |

The receiver rejects wrong size, magic, version, type, or MIDI range. Sequence suppresses
immediate duplicates and may reset after 500 ms of inactivity so a restarted companion can
reconnect without restarting the DAW.

Panic clears voices, sustain, and effect tails. UDP loss cannot block the camera or audio
threads; companion shutdown always sends panic. A heartbeat/acknowledgment channel is reserved
for v2.
