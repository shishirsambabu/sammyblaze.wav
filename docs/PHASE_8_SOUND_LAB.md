# Phase 8: performance cockpit and Sound Lab

SammyBlaze 0.4.0 adds a scalable performance cockpit based on the product visual direction:
near-black instrument surfaces, cyan routing and status accents, a live camera stage, the 3D
expression playground, compact telemetry, transport, sustain, and panic controls.

## Sound Lab

The Sound Lab is an actual synthesis editor shared by the standalone instrument and native
VST3 bridge. It exposes:

- dual oscillator shapes, blend, detune, and unison;
- attack, decay, sustain, and release;
- low-pass, high-pass, band-pass, and notch filter modes;
- cutoff, resonance, filter envelope, and performance brightness;
- patch vibrato rate and depth;
- master volume, reverb, delay mix/time, and chorus.

Edits are immutable validated `Preset` snapshots. The UI debounces physical-dial movement and
applies each snapshot without restarting the camera or cutting active notes. The built-in engine
uses an audio-thread event queue. The VST3 companion emits the same stable 21-parameter snapshot
through bridge message type `6`; the plug-in socket thread passes it through the bounded mailbox
before the audio thread applies it.

## User sounds

**Save As** writes a complete patch, master gain, brightness, custom name, and source-factory
provenance as versioned JSON. Writes are atomic, filenames are deterministic and path-safe, and
documents are strictly validated on load. User sounds live under
`%LOCALAPPDATA%\SammyBlaze\presets` by default and can be loaded or deleted from the Sound Lab.

The VST3 independently exports 24 automatable host parameters and persists every editable patch
field in DAW state. This means the companion workflow and ordinary DAW automation both remain
first-class.

## Verification

- Python synthesis, bridge, preset-store, widget, and desktop construction tests.
- Ruff lint and formatting for the changed surface.
- Native MSVC x64 Release build.
- Steinberg validator: 47 passed, 0 failed.
- Physical 60-frame camera/built-in-audio smoke test passed after install.
- FL Studio discovery and live bridge playback remain the DAW workstation smoke test.
