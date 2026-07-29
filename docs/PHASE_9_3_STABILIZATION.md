# Phase 9.3: timing, recovery, and release-footprint stabilization

## Goal

Phase 9.3 removes three gaps that still make the instrument behave like a
development build under host load or hardware failure:

1. VST note events and automation must take effect at their host-provided sample
   offsets instead of being applied to the entire block.
2. A camera that stops returning frames must recover through a bounded reopen
   policy or terminate the stream cleanly.
3. The Windows standalone must contain only the runtime modules needed by the
   performer product.

All paths remain local-first. No recovery or audio behavior may depend on a
network, LLM, or cloud service.

## Native timing and unison gates

- Host note-on, note-off, and parameter points at offset `N` affect no sample
  before `N`.
- Multiple events and parameter points in one block are processed in stable
  offset order.
- The audio callback performs no allocation, locking, logging, socket, camera,
  or Python work.
- The 1–16 unison control must not silently render a maximum of three voices.
  Any adaptive real-time budget must expose the effective value and preserve a
  true 16-voice result when the budget permits it.
- Twenty-four active notes, the heaviest supported unison/effects policy, 256
  frames at 48 kHz must remain finite and meet the established p95 target of
  2.67 ms on the development workstation.
- The release VST3 must pass the complete Steinberg validator suite.

## Camera recovery gates

- Consecutive read failures do not create an unbounded retry loop or frame
  backlog.
- Recovery attempts and total recovery time are explicitly bounded.
- An external stop request interrupts reopen waiting.
- Every superseded, failed, cancelled, or closed capture is released exactly
  once.
- A successful recovery resumes latest-frame delivery and increments an
  observable recovery generation/count.
- Exhausted recovery closes the frame stream so consumers cannot hang.

## Packaging gates

- Replace broad `collect-all` rules with explicit runtime collection for Qt
  Widgets, MediaPipe Tasks Vision, OpenCV, SoundDevice, RtMidi, the hand model,
  and `SammyBlazeAudioCore`.
- Reduce the standalone payload from the Phase 9.2 baseline of
  `1,047,945,803` bytes and `4,329` files to at most `450,000,000` bytes and
  `1,500` files.
- The packaged executable remains responsive for a ten-second offscreen startup
  smoke test.
- A packaged camera + native-audio worker reaches at least eight frames and
  stops cleanly.
- Release staging produces a manifest and SHA-256 checksum set with zero
  mismatches.

## Exit criteria

Phase 9.3 is complete only when all three tracks pass from one committed source
revision, the validated VST is installed, and the exact release artifacts are
staged on `D:`. A successful build alone is not completion.
