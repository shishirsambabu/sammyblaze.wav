# Phase 7: native plug-in and DAW bridge

## Delivered vertical slice

- Native C++20 VST3 instrument using Steinberg VST3 SDK `v3.8.0_build_66`.
- Valid Windows VST3 bundle with stereo output, MIDI input, and generated-MIDI output.
- Twenty-four voices with note-aware stealing, sustain and release envelopes, dual oscillators,
  up to three rendered unison voices, multimode filtering, smoothed gain/expression/timbre,
  motion-driven vibrato, stereo reverb, variable delay, chorus, and output limiting.
- A shared 120-sound factory library covering keys through cinematic atmospheres.
- Eight automatable parameters, including the 120-choice Factory Sound list, with DAW state
  persistence.
- Local-only direct gesture bridge; no virtual MIDI driver and no Python inside the plug-in.
- Build and explicit Steinberg validator gate on D:.
- Companion loop record/play/clear controls shared by MIDI, standalone, and VST bridge outputs.
- Bridge program-change messages switch the native factory sound without restarting a session.

## Build and validate

Prerequisites on this workstation:

```text
Visual Studio Build Tools: D:\VisualStudio\BuildTools
Windows SDK:              D:\WindowsKits\10
Steinberg VST3 SDK:       D:\SammyBlazeDeps\vst3sdk
```

Build:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-native.ps1 -Validate
```

Artifact:

```text
D:\SammyBlazeBuild\native\VST3\Release\SammyBlaze.vst3
```

For FL Studio, use the standard system location or add the D:-based install directory as a
custom plug-in search path:

```text
C:\Program Files\Common Files\VST3\SammyBlaze.vst3
D:\VST3\SammyBlaze.vst3
```

Rescan plug-ins, add `SammyBlaze` as an instrument, run the performer UI, and select
`FL Studio / VST3 bridge`.

## Bridge contract

The companion sends fixed 14-byte UDP packets to `127.0.0.1:18736`. See
`protocol/bridge-v1.md`. The socket thread validates magic, version, message type, MIDI range,
and sequence. It writes into a bounded single-producer/single-consumer queue; the audio callback
only drains that queue.

One loaded plug-in instance owns the v1 bridge port. Multi-instance routing will add a companion
broker and instance IDs without changing the audio-thread contract.

## Release gates

- Python tests and lint pass.
- Native Release build completes with MSVC x64.
- Steinberg validator self-test passes.
- VST3 bundle passes all validator tests.
- FL Studio discovery and live bridge audio are physically smoke-tested.
- The Windows bundle and VST3 are code-signed before public distribution.

## Next slices

1. Host-transport authority: BPM, PPQ, time signature, loop bars, quantization strength.
2. Sample-accurate event offsets from bridge mailbox to audio block.
3. Multi-instance broker and scene routing.
4. MPE/VST3 note expression and MIDI 2.0 capability negotiation.
5. Searchable/favorite preset browser, mapping editor, learn mode, and per-song scene automation.
6. Audio/MIDI clip export, overdub, undo, count-in, metronome, and punch recording.
7. CLAP target after the VST3 product path is stable.
