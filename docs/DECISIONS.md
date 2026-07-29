# Architecture decisions

## ADR-001: local-first live runtime

The live camera-to-sound path has no LLM or internet dependency. Agents and cloud tools are for development around the instrument, not for real-time performance.

## ADR-002: MIDI and standalone audio share one contract

Musical intent produces notes and controls once. MIDI and FluidSynth are output adapters behind `NoteSink`, which keeps routing changes from changing musical behavior.

## ADR-003: rules before custom ML

The first gesture engine is deterministic and debuggable. Custom ML is gated on recordings that demonstrate a stable rules failure, with negative examples and session-level evaluation.

## ADR-004: one owner for active notes

`NoteManager` is the only component allowed to decide which notes are active. This makes emergency stop, tracking loss, output switching, and exception cleanup testable and idempotent.

## ADR-005: native plug-in, Python companion

The DAW audio processor is C++ and never embeds Python, MediaPipe, or the camera stack. The
Python companion owns computer vision, gesture interpretation, UI, and calibration. This keeps
the DAW audio callback deterministic and lets either side evolve behind a versioned bridge.

## ADR-006: Steinberg SDK directly for the first VST3

The first native target uses Steinberg's MIT-licensed VST3 SDK directly. JUCE remains a valid
future cross-format option, but adopting it requires an explicit AGPL/commercial licensing
decision. Product delivery must not silently inherit that unresolved choice.

## ADR-007: lock-free boundary around local bridge I/O

The v1 companion bridge uses fixed-size localhost packets. Socket work runs on a background
thread and feeds a bounded SPSC queue; the plug-in audio thread performs no socket calls, locks,
allocation, logging, camera work, or Python calls.

## ADR-008: separate live and loop note ownership

`LoopTransport` reference-counts ownership conceptually between live and loop sources. A loop
note-off only reaches the sink when the performer is not also holding that note, preventing
audible note theft during overdub-like performance.

## ADR-009: hardware acquisition has a bounded cancellation contract

Native camera constructors and first-frame reads may block inside operating-system code. Camera
opening therefore runs behind bounded daemon workers with one total deadline, a process-wide
worker cap, and an external cancellation event. A late capture is abandoned and released instead
of being published. The desktop worker passes its stop event through the runtime into the camera
adapter and treats an explicitly cancelled open as a clean stop.

## ADR-010: factory DSP finiteness is a release gate

Every supported factory program must render finite output across the supported sample-rate and
brightness envelope before packaging. Standalone and native renderers contain invalid state at
their DSP boundaries and expose recoveries instead of silently propagating NaN samples. The
native gate shares filter helpers and the factory catalog with the VST build; the standalone gate
renders all factory programs through `SynthEngine`. Finiteness is necessary but not sufficient:
real-time deadline headroom remains a separate Phase 9 acceptance gate.

## ADR-011: standalone and VST share one native synthesis engine

The Python renderer remains a development compatibility path, not the commercial real-time
engine. A versioned C ABI wraps the allocation-free native `SynthEngine`; the standalone
SoundDevice callback delivers bounded commands and asks that engine for interleaved float32
audio. The VST processor schedules host and bridge commands into the same engine implementation.
This removes duplicated oscillator/filter/effect behavior and makes one DSP validation matrix
apply to both products without embedding Python in the plug-in.
