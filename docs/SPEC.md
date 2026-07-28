# Product specification

## Product promise

SammyBlaze.wav lets a performer shape harmony and expression with their hands, with a responsive local runtime that feels like an instrument rather than a gesture demo.

## MVP scope

The MVP supports two-hand chord/scale performance, named chord progressions and scales, latched
voice-led chords, stable legato melody, motion-sensitive attack, discrete gesture commands,
smoothed volume/expression/effect sends, sustain, MIDI output, and a standalone-audio adapter
boundary. It must be usable without an LLM, cloud service, or internet connection after
installation.

### In scope

- OpenCV camera capture and MediaPipe hand landmarks.
- Landmark normalization, confidence filtering, and movement features.
- Debounced gesture state machine with hold, cooldown, and neutral re-arm.
- Chord voicing for major, minor, diminished, augmented, and seventh chords.
- MIDI note and control output with guaranteed cleanup.
- Optional FluidSynth/SoundFont output behind the same output contract.
- Dry-run mode, diagnostics overlay, YAML configuration, and tests.

### Later scope

- Tempo-aware rhythm, accompaniment styles, custom scale roots, and harmonic substitutions.
- Capability-negotiated MPE and MIDI 2.0 output for per-note pitch, pressure, and timbre.
- Phrase-aware dynamics, quantization strength, loop capture, and scene/preset morphing.
- Custom gesture learning from session-partitioned recordings.
- Small static classifier and then a sequence model only where rules fail.
- Release-grade desktop routing, calibration, recording, and performance-preset workflows.

## Non-functional requirements

- Target camera-to-command latency: p95 under 100 ms on a supported laptop.
- No unbounded queues in the live path.
- No stuck notes after a camera failure, tracking loss, output switch, exception, or exit.
- A missing optional dependency produces a clear setup error, not an import-time crash for unrelated modules.
- Every gesture is observable in the overlay and event log.

## Product decisions

1. Rules before ML: the first instrument must be debuggable by a performer and engineer.
2. MIDI is the interoperability layer; standalone synthesis is a peer output adapter, not a second musical engine.
3. Musical intent is represented as commands (`next_chord`, `scale_note`, `expression`, and
   `effect_send`) rather than raw camera geometry.
4. Recorded data is append-only and session-scoped; training/evaluation splits happen by session.
