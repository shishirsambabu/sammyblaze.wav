# SammyBlaze.wav

SammyBlaze.wav is a standalone, hand-controlled musical instrument. A webcam sees expressive hand movement; a local runtime turns that movement into musical intent; the final output can be a virtual instrument through MIDI or a local SoundFont synthesizer.

The product is intentionally split into four replaceable layers:

```text
Webcam -> hand landmarks -> gesture events -> musical commands -> MIDI / standalone audio
```

The first milestone is a playable progression instrument:

- open palm held for 500 ms: arm and play the current chord
- swipe right / left: next / previous chord
- right-hand vertical position: expression/volume
- pinch: toggle arpeggiator mode
- fist or `Esc`: stop all notes immediately

The default progression is `C major -> A minor -> F major -> G major`.

## Repository map

- `docs/SPEC.md`: canonical product and engineering contract
- `docs/ARCHITECTURE.md`: runtime boundaries, latency budget, and failure handling
- `docs/GESTURE_LANGUAGE.md`: performer-facing gesture grammar
- `docs/ROADMAP.md`: staged delivery plan with exit criteria
- `docs/PHASE_4_CALIBRATION.md`: calibration and preset workflow
- `docs/PHASE_5_DATA_ML.md`: consented feature recording and ML protocol
- `docs/PHASE_6_RELEASE.md`: performer support, QA, and release gates
- `agents/registry.yaml`: AI/ML team roster, ownership, dependencies, and gates
- `agents/`: role-specific operating prompts for parallel subagents
- `src/handmusic/`: deterministic core and optional hardware adapters
- `configs/`: user-editable gesture and music mappings
- `tests/`: hardware-independent verification

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python -m handmusic --dry-run
python -m handmusic --diagnostics
```

For camera/MIDI development, install the optional runtime extras:

```powershell
python -m pip install -e ".[vision,midi,audio,ui]"
python -m handmusic --camera 0 --output midi
```

The `midi` extra provides the pure-Python Mido API. The `midi-native` extra includes both Mido and the RtMidi hardware backend, so use it when you have a native MIDI toolchain.

If the machine does not have a compiled RtMidi backend yet, use camera-only diagnostics:

```powershell
python -m handmusic --camera 0 --output null
```

The first launch should be done with `--dry-run` or a null output. Hardware adapters are optional so the core can be tested on every machine and in CI. For standalone audio, pass `--output standalone --soundfont path/to/file.sf2`.

When reporting a machine-specific issue, run `python -m handmusic --diagnostics` from the project environment and attach the text output. The command does not open the camera, MIDI port, or synthesizer.

## Development principles

- The live path is local and must not depend on an LLM or the internet.
- Rules come before custom ML. Add a classifier only after real recordings identify a repeatable failure mode.
- Treat “no intentional gesture” as a first-class negative class in future datasets.
- Split train/test data by recording session, not by frame.
- Use Git branches or worktrees for parallel agents; never let two agents edit the same files at once.

See `AGENTS.md` for repository rules and `docs/AI_TEAM.md` for the operating model.
