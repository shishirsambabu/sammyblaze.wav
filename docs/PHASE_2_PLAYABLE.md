# Phase 2 playable progression and two-hand performance

The live runtime now maps the gesture language to a selectable progression and separates the
performer’s two hands:

| Gesture | Runtime action |
|---|---|
| Left open palm held 500 ms | Arm and latch the current voiced chord |
| Left swipe right / left | Advance or reverse with smooth automatic voice leading |
| Left pinch held 180 ms | Cycle chord+scale, chord-only, scale-only, effects-only |
| Left thumb-only held 220 ms | Toggle the independent sustain pedal through MIDI CC64 |
| Left fist held 120 ms | Stop all notes and disarm |
| Right-hand horizontal position | Play a stable legato note from the selected scale |
| Right-hand downward motion | Add note velocity for keyboard-like attack |
| Right-hand pinch edge | Re-articulate the current note |
| `Esc` | Exit through the same cleanup path |
| Tracking loss for 1500 ms | Stop all notes and disarm |

The chord latch holds the left-hand harmony without requiring the performer to freeze a pose.
Chord changes are voiced in a compact keyboard register with minimum movement between inversions.
The right-hand note selector uses boundary hysteresis to prevent camera jitter from causing
unwanted neighboring notes.

The camera overlay shows the active chord voicing, melody note, mode, pedal state, last recognized
gesture, tracked-hand count, and FPS. Use `--progression` and `--scale` to choose a musical vocabulary.
Use `--output null` for camera-only testing; use `--output midi` once `.[midi-native]` and a
working RtMidi destination are installed. Use `--max-frames 1` for a bounded hardware smoke test.

The runtime keeps gesture interpretation separate from chord voicing and note delivery. This makes the progression playable with a fake sink in CI and with a DAW or standalone synth in a performer setup.
