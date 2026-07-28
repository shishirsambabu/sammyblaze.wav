# Architecture decisions

## ADR-001: local-first live runtime

The live camera-to-sound path has no LLM or internet dependency. Agents and cloud tools are for development around the instrument, not for real-time performance.

## ADR-002: MIDI and standalone audio share one contract

Musical intent produces notes and controls once. MIDI and FluidSynth are output adapters behind `NoteSink`, which keeps routing changes from changing musical behavior.

## ADR-003: rules before custom ML

The first gesture engine is deterministic and debuggable. Custom ML is gated on recordings that demonstrate a stable rules failure, with negative examples and session-level evaluation.

## ADR-004: one owner for active notes

`NoteManager` is the only component allowed to decide which notes are active. This makes emergency stop, tracking loss, output switching, and exception cleanup testable and idempotent.
