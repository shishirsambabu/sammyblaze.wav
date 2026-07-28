# System architecture

```mermaid
flowchart LR
  C[Camera capture] --> T[Hand tracker]
  T --> F[Feature extractor]
  F --> G[Gesture state machine]
  G --> I[Musical intent runtime]
  I --> V[Voice-leading engine]
  I --> M[Melody performance engine]
  V --> N[Note manager]
  M --> N
  I --> N[Note manager]
  N --> O1[MIDI output]
  N --> O2[FluidSynth output]
  T --> U[Diagnostics overlay]
  G --> U
```

## Boundaries

### Capture and tracking

`camera` owns frames and shutdown. `tracking` owns MediaPipe integration and converts vendor-specific results into `HandObservation`. No downstream module imports MediaPipe types.

### Features and gestures

`gestures.features` converts observations into normalized geometry and motion. `gestures.state_machine` turns features into discrete `GestureEvent` values. This layer owns stability, cooldown, and neutral re-arm behavior.

### Musical intent

`app.InstrumentRuntime` maps gestures to intent. It knows that “next chord” means progression navigation; it does not know how a camera landmark is represented.

`music.performance` is the musicality layer:

- `VoiceLeadingEngine` chooses compact left-hand inversions that minimize movement.
- `MelodyPerformanceEngine` adds scale locking, boundary hysteresis, motion velocity, and
  intentional re-articulation.
- The chord latch and physical sustain pedal are independent states, allowing clean harmonic
  changes or deliberately overlapping pedal harmony.

### Sound output

`music.chord_engine` maps a chord specification to MIDI note numbers. `music.note_manager` owns active-note truth and cleanup. Output adapters implement note/control delivery and are swappable.

The output contract remains MIDI-compatible today. Its next expressive extension is a
capability-negotiated MPE/MIDI 2.0 adapter for per-note pitch, pressure, and timbre without
coupling gesture interpretation to any one synthesizer.

## Threading model

```text
camera thread -> latest-frame queue(maxsize=1) -> tracker worker
tracker worker -> feature/event queue -> intent worker
intent worker -> note manager -> output adapter
UI thread reads immutable diagnostics snapshots
```

The queue policy is “latest frame wins.” Gesture events are timestamped so an overloaded UI cannot reorder musical commands.

## Latency budget

| Stage | Target |
|---|---:|
| Capture and conversion | 10 ms |
| Hand tracking | 35 ms |
| Features + state machine | 5 ms |
| Intent + voicing | 5 ms |
| Output dispatch | 10 ms |
| Headroom | 35 ms |

## Failure and safety rules

- Tracking loss beyond the configured timeout calls `NoteManager.stop_all()`.
- Any output switch stops the old output before opening the new one.
- `Esc`, fist, exception, and normal exit all converge on the same stop path.
- A note is considered active only after the output adapter accepts `note_on`.
- MIDI values are clamped to `0..127`; invalid note values fail fast.
