# Delivery roadmap

## Phase 0 — architecture and contracts

Exit criteria: repository rules, contracts, deterministic chord engine, note cleanup, test harness, and agent roster exist.

## Phase 1 — camera diagnostics (in progress)

Exit criteria: webcam opens, up to two hands are tracked, landmarks/handedness/confidence/FPS are overlaid, and clean shutdown works. The current implementation includes a bounded latest-frame capture path and hardware-independent queue tests; physical webcam verification remains an opt-in smoke test.

## Phase 2 — playable progression

Exit criteria: open palm arms, swipes navigate `C-Am-F-G`, fist/`Esc` stop, and output routing is visible.

## Phase 3 — expression and standalone audio

Exit criteria: vertical/horizontal movement controls bounded CC values, and a SoundFont adapter plays without a DAW.

## Phase 4 — calibration and presets

Exit criteria: per-user neutral pose, camera orientation, sensitivity, and routing can be saved as a versioned preset.

## Phase 5 — data and custom ML

Exit criteria: consented sessions are recorded, labeled, quality-checked, session-split, and benchmarked against rules before a model is shipped.

## Phase 6 — performer product

Exit criteria: desktop UI, installer, diagnostics, crash-safe note cleanup, performance telemetry, documentation, and release checklist are complete.
