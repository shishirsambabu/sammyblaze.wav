# Delivery roadmap

## Phase 0 — architecture and contracts

Exit criteria: repository rules, contracts, deterministic chord engine, note cleanup, test harness, and agent roster exist.

## Phase 1 — camera diagnostics (delivered)

Exit criteria: webcam opens, up to two hands are tracked, landmarks/handedness/confidence/FPS are
overlaid, and clean shutdown works. The Windows capture path now probes DirectShow, Media
Foundation, and automatic backends, verifies a real first frame, prevents stale-frame buildup,
and falls back to camera 0. It has passed physical 640x480 webcam and UI-worker smoke tests.

## Phase 2 — playable progression (in progress)

Exit criteria: the left hand arms and navigates a selectable progression, the right hand plays a
selectable scale, sustain and mode changes are gesture-controlled, tracking loss stops notes, and
output routing/chord/mode state is visible. The current implementation adds latched chords,
minimum-motion inversion selection, stable legato melody mapping, movement-sensitive velocity,
pinch re-articulation, and desktop/overlay note feedback.

## Phase 3 — expression and standalone audio (in progress)

Exit criteria: vertical/horizontal/depth/pinch movement controls smoothed bounded volume,
expression, pan, reverb, delay, and chorus values, and the app plays without a DAW. The current
implementation includes a physically verified SoundDevice engine, 24-voice bounded polyphony,
dual oscillators, ADSR, filters, unison, effects, limiting, and 120 factory sounds; FluidSynth
remains an optional external SoundFont route.

## Phase 4 — calibration and presets (in progress)

Exit criteria: per-user neutral pose, camera orientation, sensitivity, and routing can be saved as a versioned preset. The current implementation covers median-based sample calibration, atomic JSON persistence, preset loading, and runtime application.

## Phase 5 — data and custom ML (in progress)

Exit criteria: consented sessions are recorded, labeled, quality-checked, session-split, and benchmarked against rules before a model is shipped. The current implementation covers append-only feature recording, a negative-class-friendly schema, session-safe splitting, and an optional Random Forest baseline.

## Phase 6 — performer product

Exit criteria: desktop UI, installer, diagnostics, crash-safe note cleanup, performance telemetry, documentation, and release checklist are complete.

The current implementation establishes the support-safe diagnostics command, deterministic CI
release gate, performer QA/release runbook, idempotent shutdown cleanup, bounded live performance
telemetry, integrated video canvas, and a desktop control surface. Signed installer packaging and
crash-recovery proof remain the next Phase 6 slices.

## Phase 7 — native DAW instrument (in progress)

Exit criteria: a native VST3 can be loaded by FL Studio, accepts host MIDI and direct camera
companion control, renders sound and effects without Python on the audio thread, persists
automatable state, and passes Steinberg validation.

The current slice delivers a validated C++20 VST3, localhost gesture bridge, 24-voice dual-
oscillator synth, ADSR, multimode filters, unison, sustain, parameter smoothing,
reverb/delay/chorus, a shared 120-sound library, live bridge program and full patch changes,
24 automatable DAW parameters, complete patch state restoration, and a D:-based build. Physical
FL Studio discovery is the remaining workstation smoke test. Host-synchronized
PPQ looping, multi-instance routing, MPE/note expression, signing, and installer integration are
next.

## Phase 8 — performance workstation

Exit criteria: tempo/PPQ-aware loop scenes, quantize and swing, overdub/undo, count-in,
metronome, clip export, scene automation, mapping learn, multi-instance routing, MPE/MIDI 2.0,
and release-grade signing are verified across supported DAWs.

The first Phase 8 slice is delivered: a scalable dark-cyan cockpit, dedicated Sound Lab,
18 hardware-style sound controls, live standalone/VST3 patch editing, and versioned local user
preset save/load/delete. Tempo/PPQ-aware looping and the remaining workstation functions are
the next slices.

## Phase 9 — instrument kernel stabilization (in progress)

Exit criteria: camera and audio startup are bounded and cancellable; shutdown is deterministic;
all factory programs remain finite in standalone and native renderers; audio failures are
performer-visible; live UI commands cross thread boundaries through bounded queues; and measured
standalone/native polyphony meets the supported real-time budget with safety headroom.

Phase 9.1 delivers bounded, cancellable Windows camera opening, clean desktop-worker cancellation,
finite-value containment and exhaustive 120-program DSP gates for both renderers, native
multi-rate DSP validation, visible standalone callback/xrun diagnostics, truthful arm/sustain
state, and bounded UI-to-runtime command marshalling. Physical acceptance passed five CLI camera
open/track/close cycles and three desktop-worker start/stop cycles on the development machine.

Phase 9.2 delivers one allocation-free C++ `SynthEngine` shared by the standalone application and
VST3, a versioned local C ABI, a bounded SoundDevice adapter, explicit development fallback
visibility, deterministic Windows release staging, and SHA-256 manifests. The native gate renders
all 120 factory programs at five sample rates, verifies zero steady-state render allocations,
passes the full 47-test Steinberg VST3 suite, and repeatedly meets the 24-voice 256-frame p95
target of 2.67 ms with more than 2x audio-deadline headroom on the development machine.

Remaining Phase 9 work: add steady-state camera-read failure recovery, make VST MIDI and
automation sample-accurate, prove actual SoundDevice callback/xrun performance in long hardware
soaks, sign Windows binaries, and complete repeated clean-machine hardware/DAW compatibility
tests.
