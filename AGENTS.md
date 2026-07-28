# SammyBlaze.wav agent guidance

SammyBlaze.wav is a real-time, hand-controlled musical instrument. Read `docs/SPEC.md` and the relevant ownership entry in `agents/registry.yaml` before changing code.

## Non-negotiable runtime rules

- The performer-facing runtime must work without an LLM, internet connection, or cloud service.
- Keep landmark detection, gesture interpretation, musical intent, and sound output as separate boundaries.
- Gesture recognition must never block the camera/render thread.
- The latest frame wins; never build an unbounded camera backlog.
- Every `note_on` must have a corresponding `note_off`, including tracking loss, output changes, exceptions, and shutdown.
- Discrete gestures require confidence, stability, cooldown, and neutral re-arm rules.
- Continuous controls must be smoothed and bounded to MIDI-safe ranges.
- Never destructively modify recordings, processed data, or model artifacts.
- Do not add dependencies without documenting the reason and runtime impact.

## Agent workflow

1. Claim a focused role from `agents/registry.yaml`.
2. Work only inside the role's owned paths unless the lead architect approves a contract change.
3. Add or update tests for deterministic logic.
4. Run `python -m pytest` before handing off.
5. Update the relevant roadmap item and decision record.

Use one branch or worktree per role. The lead architect owns cross-boundary integration and resolves contract changes.
