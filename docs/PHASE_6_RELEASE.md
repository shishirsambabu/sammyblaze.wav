# Phase 6 — performer product foundation

Phase 6 turns the working instrument into something a performer can install, test, and support.
This first slice adds a hardware-free diagnostics report and a repeatable release gate. It keeps
the live path local and avoids opening camera or MIDI devices during support collection.

## Support command

Run this from the environment that launches the instrument:

```powershell
python -m handmusic --diagnostics
```

The report includes the interpreter, platform, editable package version, dependency versions,
hand-landmarker model status, and a read-only MIDI output-port probe. It is safe to run while a
DAW or synth is open; the command does not send MIDI, start a camera, or load FluidSynth.

For the D: Python 3.12 performer environment used during native MIDI bring-up:

```powershell
D:\Python312\python.exe -m handmusic --diagnostics
D:\Python312\python.exe -m handmusic --camera 0 --output midi --max-frames 1
```

The bounded camera command is the hardware smoke test. Remove `--max-frames 1` for a normal
session after confirming the camera preview and MIDI port are correct.

The `midi-native` extra includes the Mido API and RtMidi backend together, so a fresh native MIDI
environment only needs:

```powershell
python -m pip install -e ".[midi-native]"
```

## Release gate

Every change must pass the following in a clean environment:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m handmusic --dry-run
python -m handmusic --diagnostics
```

Before a performer build is published, run the optional checks that match the target machine:

1. `python -m handmusic --camera 0 --output null --max-frames 1`
2. `python -m handmusic --camera 0 --output midi --max-frames 1`
3. `python -m handmusic --output standalone --soundfont <path> --camera 0 --max-frames 1`
4. Open-palm arm, swipe progression, fist stop, and tracking-loss note cleanup.
5. Calibration save/load and a fresh diagnostics report from the installed build.

Hardware checks are intentionally outside CI. CI verifies deterministic behavior; the release
operator verifies the machine-specific camera, MIDI driver, audio backend, and model file.

## Remaining Phase 6 slices

- desktop performer UI with explicit device selection and visible connection state;
- reproducible Windows wheel/installer build with signed artifacts;
- runtime performance telemetry for frame age, gesture latency, and dropped frames;
- crash-recovery harness that proves all active notes are released on process shutdown.
