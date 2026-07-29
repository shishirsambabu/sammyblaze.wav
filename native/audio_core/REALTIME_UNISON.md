# Real-time unison contract

The public unison value is the requested number of independently tuned oscillator
lanes and is valid from 1 through 16. The engine never rewrites or silently clamps
that request.

At six or fewer active notes, all 16 requested lanes render continuously on every
sample. At higher polyphony, the engine enforces a fixed budget of 96 oscillator
lanes per sample. Each voice receives an equal per-sample lane budget and renders
a stable, evenly spaced subset spanning the requested detune range. The subset
does not rotate from sample to sample, avoiding modulation and discontinuities
caused by oscillator swapping.

Gain is normalized by `1 / sqrt(rendered lanes)`, which is never greater than
unity. It does not multiply by `requested / rendered`, so the quality strategy
cannot create a compensation spike when only one lane renders.

This policy bounds callback work without lying about the patch:

| Active notes | Requested lanes | Lanes rendered per note/sample | Rotation |
|---:|---:|---:|---|
| 1 | 16 | 16 | No |
| 6 | 16 | 16 | No |
| 12 | 16 | 8 | Stable subset |
| 24 | 16 | 4 | Stable subset |

The C++ engine exposes `requestedUnisonVoices()`,
`renderedUnisonLanesPerVoice()`, `unisonQualityLimited()`, and
`oscillatorWorkCount()` for diagnostics and deterministic tests. Optional C ABI
query exports expose the first three values to standalone clients. The ABI
version remains 1 and the v1 patch stays exactly 96 bytes.

The Phase 9.3 benchmark uses the maximum case (24 notes requesting 16 lanes),
prints the requested and rendered lane counts, and enforces the existing
2.67 ms p95 deadline.
