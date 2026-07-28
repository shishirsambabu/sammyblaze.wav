# Phase 3 expression and standalone audio

Right-hand position now maps continuously through an exponential smoother:

- vertical position -> MIDI CC 11 expression (`0..127`)
- horizontal position -> MIDI CC 10 pan (`0..127`)
- vertical position -> MIDI CC 7 channel volume (`0..127`)
- pinch distance -> MIDI CC 91 reverb send (`0..127`)
- calibrated depth -> MIDI CC 94 delay send (`0..127`)
- distance from horizontal neutral -> MIDI CC 93 chorus send (`0..127`)

The left hand remains responsible for progression decisions, mode changes, sustain, and chord
voicing. Chords are latched and revoiced automatically into compact inversions. The right hand
plays the selected scale with hysteresis-stabilized legato transitions, motion-derived velocity,
and pinch re-articulation while it shapes expression and effects. All controls are emitted through
the same `NoteManager` contract as MIDI notes, so a MIDI device and FluidSynth receive identical
intent.

## MIDI mode

Install the native backend when a C++ toolchain is available:

```powershell
python -m pip install -e ".[midi-native]"
python -m handmusic --camera 0 --output midi
```

## Standalone mode

Install the Python wrapper and the FluidSynth native library, then provide a SoundFont:

```powershell
python -m pip install -e ".[audio]"
python -m handmusic --camera 0 --output standalone --soundfont path/to/instrument.sf2
```

Use `--output null --max-frames 1` to validate camera/tracking independently of either audio
backend.
