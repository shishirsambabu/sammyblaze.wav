# Phase 9.2: shared native audio core

## Objective

The standalone performer and VST3 must render the same native synthesis engine. Python remains
responsible for camera tracking, musical intent, UI, and bounded command delivery; it must not
generate samples or run per-sample DSP in the real-time callback.

## Runtime boundary

```text
Python intent/UI -> bounded callback event queue -> C ABI -> native SynthEngine -> stereo float32
VST3 host/bridge -> VST Processor scheduling -> same native SynthEngine -> stereo float32
```

The native engine is created and configured before streaming. Rendering performs no allocation,
locking, filesystem, socket, logging, Python, or camera work.

## C ABI v1

The Windows library is `SammyBlazeAudioCore.dll`. All functions are `noexcept` at the C++
boundary, validate null handles and ranges, and return an error code instead of allowing an
exception to cross the ABI.

Required exports:

- `sbw_audio_core_abi_version`
- `sbw_audio_core_create`
- `sbw_audio_core_destroy`
- `sbw_audio_core_note_on`
- `sbw_audio_core_note_off`
- `sbw_audio_core_control_change`
- `sbw_audio_core_program_change`
- `sbw_audio_core_apply_patch`
- `sbw_audio_core_render_interleaved`
- `sbw_audio_core_panic`
- `sbw_audio_core_active_voice_count`
- `sbw_audio_core_nonfinite_recovery_count`

`SbwAudioPatchV1` uses the platform C ABI with this exact field order:

```text
uint32 struct_size
uint32 abi_version
uint32 program
uint32 waveform_a
uint32 waveform_b
uint32 filter_type
uint32 unison_voices
float waveform_mix
float attack_ms
float decay_ms
float sustain
float release_ms
float filter_cutoff_hz
float filter_resonance
float filter_envelope
float detune_cents
float vibrato_rate_hz
float vibrato_depth_semitones
float reverb_mix
float delay_mix
float delay_time_ms
float chorus_mix
float master_gain
float brightness
```

The ABI version is `1`. `struct_size` permits rejecting truncated callers and extending a future
structure without silently reinterpreting old memory.

## Failure policy

- A missing or incompatible DLL produces an actionable startup error and may use the explicitly
  reported Python compatibility renderer during development.
- The callback command queue is bounded. Overflow records a health failure and converges on
  native panic; it never blocks the callback.
- Native non-finite recovery and SoundDevice underflow/overflow counts are visible to the
  performer.
- Closing the output drains no new music commands, calls panic, stops the stream, destroys the
  native handle exactly once, and is idempotent.

## Acceptance gates

1. The VST3 and standalone adapter both use the same `SynthEngine` implementation.
2. All 120 factory programs render finite output through the DLL.
3. Note-on/off, sustain release, program changes, live full-precision patches, panic, and repeated
   create/destroy are covered.
4. At 48 kHz and 256 frames, 24 sustained voices render at p95 below 2.67 ms on the supported
   development machine.
5. The standalone UI passes physical camera plus native-audio start/stop testing.
6. PyInstaller staging contains the DLL; the release bundle separately contains the VST3 and
   checksums.
