# Phase 2 playable progression and two-hand performance

The live runtime now maps the gesture language to a selectable progression and separates the
performer’s two hands:

| Gesture | Runtime action |
|---|---|
| Left open palm held 500 ms | Arm and play the current chord |
| Left swipe right / left | Advance or reverse the selected progression |
| Left pinch held 180 ms | Cycle chord+scale, chord-only, scale-only, effects-only |
| Left thumb-only held 220 ms | Toggle sustained chords through MIDI CC64 |
| Left fist held 120 ms | Stop all notes and disarm |
| Right-hand horizontal position | Play a note from the selected scale |
| `Esc` | Exit through the same cleanup path |
| Tracking loss for 500 ms | Stop all notes and disarm |

The camera overlay shows the active chord, mode, sustain state, last recognized gesture,
tracked-hand count, and FPS. Use `--progression` and `--scale` to choose a musical vocabulary.
Use `--output null` for camera-only testing; use `--output midi` once `.[midi-native]` and a
working RtMidi destination are installed. Use `--max-frames 1` for a bounded hardware smoke test.

The runtime keeps gesture interpretation separate from chord voicing and note delivery. This makes the progression playable with a fake sink in CI and with a DAW or standalone synth in a performer setup.
