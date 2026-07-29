# Native plug-in and DSP engineer

## Mission

Build the real-time-safe native instrument and effects layer for VST3 and future plug-in formats.

## Owns

- `native/plugin/`
- root native CMake files

## Working contract

- No allocation, locks, socket calls, logging, Python, or camera work in the audio callback.
- All external commands cross a bounded mailbox.
- Parameters are smoothed, automatable, bounded, and persisted.
- Panic clears voices, sustain, and effect tails.
- Build Release x64 and run the official format validator before handoff.

## Exit gate

The complete bundle passes validator tests, survives repeated initialize/terminate and
setProcessing transitions, and produces bounded audio at every supported sample rate.
