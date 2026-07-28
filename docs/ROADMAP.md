# Delivery roadmap

## Phase 0 — architecture and contracts

Exit criteria: repository rules, contracts, deterministic chord engine, note cleanup, test harness, and agent roster exist.

## Phase 1 — camera diagnostics (in progress)

Exit criteria: webcam opens, up to two hands are tracked, landmarks/handedness/confidence/FPS are overlaid, and clean shutdown works. The current implementation includes a bounded latest-frame capture path and hardware-independent queue tests; physical webcam verification remains an opt-in smoke test.

## Phase 2 — playable progression (in progress)

Exit criteria: the left hand arms and navigates a selectable progression, the right hand plays a
selectable scale, sustain and mode changes are gesture-controlled, tracking loss stops notes, and
output routing/chord/mode state is visible. The current implementation adds latched chords,
minimum-motion inversion selection, stable legato melody mapping, movement-sensitive velocity,
pinch re-articulation, and desktop/overlay note feedback.

## Phase 3 — expression and standalone audio (in progress)

Exit criteria: vertical/horizontal/depth/pinch movement controls smoothed bounded volume,
expression, pan, reverb, delay, and chorus CC values, and a SoundFont adapter plays without a DAW.
The current implementation covers mapping and adapter hardening; physical FluidSynth verification
remains environment-dependent.

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
