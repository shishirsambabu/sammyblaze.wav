# Audio/MIDI subagent

Implement output adapters behind one note/control contract. Keep optional `mido`, `python-rtmidi`, and FluidSynth imports lazy. Make cleanup idempotent and test with a fake sink. Never let a hardware error leave active notes in the manager.

Required handoff: supported devices, routing instructions, failure behavior, and cleanup evidence.
