# Phase 9.1: native DSP stability

## Scope

This slice hardens the allocation-free native audio path against the factory-filter instability
found during the Phase 9 hostile audit. It deliberately does not change VST event timing,
automation scheduling, the Python camera runtime, or the Python standalone renderer.

## Stability contract

The native synth keeps its existing Chamberlin state-variable filter topology and damping map:

```text
damping = 1.95 - resonance * 1.55
requested coefficient = 2 * sin(pi * cutoff / sample_rate)
```

The old fixed coefficient ceiling of `0.95` was unsafe at low resonance. For this state
transition, the stability boundary is:

```text
coefficient^2 + 2 * damping * coefficient < 4
```

The native path now applies a 5% safety margin below the resonance-dependent boundary. Filter
state and input are checked for finite values without allocation, locks, or exceptions. A
non-finite state is reset locally and emits silence for that filter frame. The final plug-in
output also has a finite-value containment guard.

The Python standalone renderer still uses the legacy fixed coefficient ceiling. Its filter must
adopt the same helper equations in its separately owned Phase 9 standalone slice before the two
renderers regain coefficient-level parity.

## Offline release gate

`SammyBlazeDspValidation` compiles the same header-only filter functions and factory catalog used
by the VST3. It validates:

- all 120 factory programs;
- 32, 44.1, 48, 96, and 192 kHz;
- minimum, neutral, and maximum performance brightness;
- swept filter envelopes;
- white-noise stress across cutoff and resonance extremes;
- the analytical stability boundary;
- finite filter state and output.

Run the native DSP gate, Release build, validator self-test, and official VST3 validator:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-native.ps1 -Validate
```
