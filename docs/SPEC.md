# Product specification

## Product promise

SammyBlaze.wav lets a performer shape harmony and expression with their hands, with a responsive local runtime that feels like an instrument rather than a gesture demo.

## MVP scope

The MVP supports seven-shape left-hand harmony, chord-relative right-hand melody, latched
voice-led chords, stable legato movement, a designated scale-mode gesture, continuous 3D
expression, sustain, bounded loop capture, MIDI/standalone output, and a native VST3 bridge.
It must be usable without an LLM, cloud service, or internet connection after installation.

### In scope

- OpenCV camera capture and MediaPipe hand landmarks.
- Landmark normalization, confidence filtering, and movement features.
- Debounced gesture state machine with hold, cooldown, and neutral re-arm.
- Chord voicing for major, minor, diminished, augmented, and seventh chords.
- MIDI note and control output with guaranteed cleanup.
- Optional FluidSynth/SoundFont output behind the same output contract.
- Direct built-in polyphonic synthesis with at least 100 stable factory sounds.
- Native VST3 instrument with localhost gesture control and ordinary host MIDI.
- Loop record/play/clear with independent live and loop note ownership.
- Dry-run mode, diagnostics overlay, YAML configuration, and tests.

### Later scope

- Tempo-aware rhythm, accompaniment styles, custom scale roots, and harmonic substitutions.
- Capability-negotiated MPE and MIDI 2.0 output for per-note pitch, pressure, and timbre.
- Phrase-aware dynamics, host-synchronized quantization, overdub/undo, and scene/preset morphing.
- Custom gesture learning from session-partitioned recordings.
- Small static classifier and then a sequence model only where rules fail.
- Release-grade desktop routing, calibration, recording, and performance-preset workflows.

## Non-functional requirements

- Target camera-to-command latency: p95 under 100 ms on a supported laptop.
- No unbounded queues in the live path.
- No stuck notes after a camera failure, tracking loss, output switch, exception, or exit.
- No socket, camera, Python, lock, or allocation work in the DAW audio callback.
- A missing optional dependency produces a clear setup error, not an import-time crash for unrelated modules.
- Every gesture is observable in the overlay and event log.

## Product decisions

1. Rules before ML: the first instrument must be debuggable by a performer and engineer.
2. MIDI-compatible note/control intent is the interoperability layer; standalone, MIDI, and VST3
   are peer destinations.
3. Musical intent is represented as commands (`next_chord`, `scale_note`, `expression`, and
   `effect_send`) rather than raw camera geometry.
4. Recorded data is append-only and session-scoped; training/evaluation splits happen by session.
