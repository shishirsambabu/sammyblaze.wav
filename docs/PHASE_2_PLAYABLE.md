# Phase 2 playable progression

The live runtime now maps the v1 gesture language to the default progression:

| Gesture | Runtime action |
|---|---|
| Open palm held 500 ms | Arm and play the current chord |
| Swipe right | Advance `C -> Am -> F -> G` and retrigger notes |
| Swipe left | Move backward and retrigger notes |
| Fist held 120 ms | Stop all notes and disarm |
| `Esc` | Exit through the same cleanup path |
| Tracking loss for 500 ms | Stop all notes and disarm |

The camera overlay shows the active chord, last recognized gesture, tracked-hand count, and FPS. Use `--output null` for camera-only testing; use `--output midi` once `.[midi-native]` and a working RtMidi destination are installed. Use `--max-frames 1` for a bounded hardware smoke test.

The runtime keeps gesture interpretation separate from chord voicing and note delivery. This makes the progression playable with a fake sink in CI and with a DAW or standalone synth in a performer setup.
