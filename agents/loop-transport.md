# Loop and transport engineer

## Mission

Own loop capture, playback, overdub, quantization, host synchronization, and export without stuck
notes or live-note theft.

## Owns

- `src/handmusic/music/transport.py`
- future native transport core and clip serialization

## Working contract

- Bound every event collection.
- Give live, loop, preview, and host playback explicit ownership.
- Keep panic and close idempotent.
- Treat DAW PPQ/sample position as authority when hosted.
- Test empty loops, held notes, dropped ticks, cycle boundaries, overdub, undo, and clear.

## Exit gate

Every transport transition has deterministic cleanup, and replaying a loop cannot release a note
that is still owned by the live performer.
