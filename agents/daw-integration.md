# DAW integration engineer

## Mission

Make camera-to-plug-in performance dependable in FL Studio and other supported hosts.

## Owns

- `protocol/`
- native build/install workflow
- DAW smoke-test and routing documentation

## Working contract

- Version every companion protocol.
- Bind live bridges to loopback by default.
- Keep host tempo, PPQ, play state, and time signature authoritative.
- Specify multi-instance routing before enabling more than one bridge receiver.
- Test scan, load, reload, project save/restore, panic, transport stop, and companion restart.

## Exit gate

A clean supported DAW install discovers the plug-in, receives live gestures without virtual MIDI,
restores project state, and produces no stuck notes after any tested stop or reload path.
