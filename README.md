# SammyBlaze.wav

SammyBlaze.wav is a local-first, hand-controlled performance instrument. A webcam sees
expressive hand movement; a deterministic musical runtime turns it into harmony, melody,
continuous expression, and loops; sound can come from MIDI, a local SoundFont, or the native
SammyBlaze VST3 loaded in a DAW.

The product is intentionally split into four replaceable layers:

```text
Webcam -> hand landmarks -> gestures + 3D expression -> musical intent
       -> MIDI / standalone audio / localhost VST3 bridge
```

The current performer milestone is a two-hand keyboardist engine:

- Seven stable left-hand shapes select I, ii, iii, IV, V, vi, and vii from a style-specific
  chord bank. Chords are latched and automatically voice-led into a keyboard register.
- A left pinch is the designated lead-mode gesture. It cycles adaptive, color, pentatonic,
  blues, and chord-tone palettes.
- A left fist or the red `PANIC` button releases every note immediately.
- Right-hand horizontal position plays stable legato notes from the active chord's root and
  quality. A chord change retunes the lead without losing the performer’s horizontal lane.
- Right-hand movement adds vibrato; height shapes dynamics; depth shapes expression and
  brightness; pinch re-articulates the note and adds reverb.
- The 3D expression playground displays X/Y/Z position, motion trail, vibrato, expression,
  timbre, and effect sends in real time.
- Sustain is independent of chord latching. Loop recording captures notes and expression,
  then plays them while live notes remain independently owned.

The style selector provides pop, anthem, minor-drive, jazz ii-V-I, blues, cinematic, and
neo-soul chord banks. The lead engine chooses quality-aware scales including Ionian, Lydian,
Aeolian, Dorian, Mixolydian, Altered, Locrian, diminished, whole-tone, pentatonic, and blues.

## Repository map

- `docs/SPEC.md`: canonical product and engineering contract
- `docs/ARCHITECTURE.md`: runtime boundaries, latency budget, and failure handling
- `docs/GESTURE_LANGUAGE.md`: performer-facing gesture grammar
- `docs/ROADMAP.md`: staged delivery plan with exit criteria
- `docs/PHASE_4_CALIBRATION.md`: calibration and preset workflow
- `docs/PHASE_5_DATA_ML.md`: consented feature recording and ML protocol
- `docs/PHASE_6_RELEASE.md`: performer support, QA, and release gates
- `docs/PHASE_7_NATIVE_PLUGIN.md`: native VST3, bridge, validation, and DAW roadmap
- `agents/registry.yaml`: AI/ML team roster, ownership, dependencies, and gates
- `agents/`: role-specific operating prompts for parallel subagents
- `src/handmusic/`: deterministic core and optional hardware adapters
- `native/plugin/`: real-time-safe C++ VST3 processor and localhost receiver
- `protocol/bridge-v1.md`: versioned companion-to-plug-in packet contract
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
python -m handmusic --ui
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

Camera sessions print frame age, dropped-frame, and gesture-latency telemetry on exit. Add `--telemetry-json path/to/session-telemetry.json` to save the bounded report for later review.

The optional `--ui` command opens the desktop performer control surface. It provides camera,
MIDI/VST3 routing, chord-bank and starting lead-mode selection, camera and 3D expression
canvases, record/play/clear loop controls, sustain, panic, live voicing state, and telemetry.
Install the UI extra first with `python -m pip install -e ".[ui]"`.

For a specific playable setup:

```powershell
python -m handmusic --camera 0 --output midi --progression blues --scale blues
```

## FL Studio / VST3

The repository includes a native C++20 VST3 instrument built directly against Steinberg's
MIT-licensed VST3 SDK. It accepts ordinary host MIDI and the direct SammyBlaze localhost bridge,
then synthesizes stereo audio with automatable gain, vibrato, expression, brightness, reverb,
delay, and chorus.

Build and run Steinberg's validator:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-native.ps1 -Validate
```

The validated bundle is written to:

```text
D:\SammyBlazeBuild\native\VST3\Release\SammyBlaze.vst3
```

This workstation also has the bundle installed at `D:\VST3\SammyBlaze.vst3`; add `D:\VST3` to
FL Studio's plug-in search paths and rescan. Load `SammyBlaze`, choose
**FL Studio / VST3 bridge** in the performer UI, and start the camera. The plug-in receives the
same chords, melody, sustain, loop, and expression stream over `127.0.0.1:18736`. The bridge is
local-only and never requires the internet.

To create a Windows development bundle, run `powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1`. The bundle is unsigned until a production code-signing certificate is configured.

## Development principles

- The live path is local and must not depend on an LLM or the internet.
- Rules come before custom ML. Add a classifier only after real recordings identify a repeatable failure mode.
- Treat “no intentional gesture” as a first-class negative class in future datasets.
- Split train/test data by recording session, not by frame.
- Use Git branches or worktrees for parallel agents; never let two agents edit the same files at once.

See `AGENTS.md` for repository rules and `docs/AI_TEAM.md` for the operating model.
