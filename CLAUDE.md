# Claude Code project instructions

You are contributing to SammyBlaze.wav, a standalone hand-controlled musical instrument.

Before architectural work, read:

1. `docs/SPEC.md`
2. `docs/ARCHITECTURE.md`
3. the role definition in `agents/` that matches the task

Keep the runtime local-first. Codex/Claude may build, test, review, and analyze recordings; they are not part of the live camera-to-sound loop. Preserve the public contracts in `src/handmusic/common/models.py` and `src/handmusic/common/events.py` unless the change includes tests and an architecture note.

Run `python -m pytest` for every code change. Prefer small, composable modules over a single camera script. Do not hide MIDI cleanup in UI code.
