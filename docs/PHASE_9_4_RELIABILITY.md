# Phase 9.4: hardware soak and DAW acceptance

## Purpose

Phase 9.4 turns short smoke tests into repeatable evidence about real callback,
camera-recovery, and DAW-host behavior. A passing unit test or Steinberg validator
run does not substitute for a sustained hardware callback or an actual host scan.

All reports are machine-readable JSON. A report must identify its inputs, limits,
observations, pass/fail reasons, and whether it used real hardware, diagnostic
fault injection, or a simulated test double.

## Native audio gates

- Run the shared C++ core through the actual SoundDevice output callback.
- Exercise 24 active notes, requested 16-lane unison, sustain, and the factory
  effect path at low master gain.
- Development gate: at least 60 seconds at 48 kHz and 256 samples.
- Release gate: at least 30 minutes each at 128 and 256 samples on every
  supported Windows audio backend/device combination.
- No SoundDevice underflow/overflow status, render failure, non-finite recovery,
  command-queue overflow, dropped diagnostic report, or callback deadline miss.
- Callback work p95 must remain at or below 50% of the audio deadline.
- The report records the selected device, host API, sample rate, block size,
  callback count, timing percentiles, ABI version, and concrete DLL path.

## Camera gates

- A diagnostic soak performs at least ten forced close/reopen cycles against the
  real camera, receives a frame after every replacement generation, and remains
  above 20 effective FPS outside recovery windows.
- Every recovery must complete within the configured bounded deadline.
- Recovery lifecycle states are visible to the desktop performer: opening,
  running, recovering, recovered, failed, and stopped.
- Observer failures cannot interrupt capture or leak a camera handle.
- Diagnostic forced reopen is not labeled as physical disconnect evidence.
- Release acceptance separately requires three physical unplug/replug cycles and
  one unplug-until-exhaustion cycle with safe terminal shutdown.

## DAW gates

The release VST3 must first pass hash comparison and the complete Steinberg
validator suite. Each supported DAW then needs host-specific evidence for:

1. verified rescan and one unambiguous x64 instrument entry;
2. MIDI note, chord, sustain, note-off, panic, and stereo audio behavior;
3. sample-accurate automation without clicks for gain, expression, effects, and
   unison controls;
4. exact project save/reopen restoration of program, patch, parameters, and
   routing;
5. four isolated instances under load;
6. companion bridge connect, target routing, restart/reconnect, and companion
   crash behavior.

## Development-machine DAW audit

FL Studio is not installed or registered on the Phase 9.4 development machine.
No Image-Line executable, uninstall record, App Path, Start Menu shortcut,
configuration directory, or plug-in search-path evidence was found. `D:\VST3`
contains one readable SammyBlaze VST3, but it is not proven to be an FL Studio
search path.

Therefore the FL Studio host gate is blocked, not passed. The future installer
should default to the standard 64-bit VST3 location under
`C:\Program Files\Common Files\VST3`; a D:-drive location remains an explicit
advanced option.

## Phase 9.4 development evidence

The automated development gate passed from committed source revision
`7b86b82d1a90247a172dbafe4c01e7bbc3f786c2`:

- The real SoundDevice/WASAPI callback ran for 60 seconds at 48 kHz and
  256 frames on `Speaker (Realtek(R) Audio)`. It produced 11,259 measured
  callbacks with zero status events, deadline misses, render failures,
  non-finite recoveries, queue overflows, or dropped reports. Callback p95 was
  1.3585 ms against a 5.3333 ms deadline.
- The real DirectShow camera ran for 60 seconds, delivered 1,510 frames at
  25.1667 FPS, and passed all ten diagnostic close/reopen recoveries. The
  slowest first-frame recovery was 1.281 seconds and shutdown left no live
  worker.
- Ruff and all 491 collected Python tests passed.
- The shared native engine gate passed its allocation, finiteness, C ABI,
  scheduling, unison, sustain, and panic checks. Its 24-note benchmark p95 was
  2.2242 ms at a 5.3333 ms deadline.
- The release VST3 passed 47/47 Steinberg validator tests both before and after
  staging.
- The exact-revision standalone bundle passed dependency probing and a
  strict-native eight-frame physical camera/synth smoke. The bundle is
  361,238,425 bytes across 292 files.
- Release staging verified all 296 SHA-256 entries without a mismatch. The
  installed `D:\VST3\SammyBlaze.vst3` binary is byte-identical to the staged
  candidate.

Machine-readable evidence is stored under
`D:\SammyBlazeValidation\phase-9.4`, and the candidate is staged under
`D:\SammyBlazeRelease\0.4.0-phase9.4-rc`.

## Completion rule

Phase 9.4 automated work is complete only when audio and camera JSON reports pass
from the same committed source as the validated and staged VST3. Full Phase 9.4
release acceptance additionally requires the 30-minute 128/256-frame audio
matrix, physical camera unplug/replug gates, and FL Studio host gates. Those
remaining checks are deliberately reported as pending or blocked rather than
passed.
