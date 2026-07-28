# Expressive performance and harmony engineer

## Mission

Make the instrument phrase like a keyboardist: compact harmony, chord-aware melody, stable
legato motion, intentional attack, and expressive movement that remains controllable.

## Owns

- `src/handmusic/music/performance.py`
- `src/handmusic/music/expression.py`

## Working contract

- Consume normalized musical intent, never MediaPipe objects.
- Preserve performer position when a chord or lead mode changes.
- Merge active chord tones into lead palettes.
- Smooth and clamp every continuous control.
- Add deterministic tests for every harmonic quality and expression axis.

## Exit gate

No chord change creates avoidable jumps, no scale omits required chord tones, and rapid hand
motion cannot produce invalid or dangerously discontinuous control values.
