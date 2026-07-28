# Gesture language v2

Finger tuples are ordered **index, middle, ring, pinky, thumb**. A chord pose must remain stable
for 180 ms with low hand velocity. Holding the same pose does not retrigger it.

## Left hand: harmony

| Shape | Finger tuple | Degree | Default pop chord |
|---|---|---:|---|
| Index | `10000` | I | Cmaj7 |
| Index + middle | `11000` | ii | Dm7 |
| Three fingers | `11100` | iii | Em7 |
| Four fingers | `11110` | IV | Fmaj7 |
| Open palm | `11111` | V | G7 |
| Shaka | `00011` | vi | Am7 |
| Wide L | `10001` | vii | Bm7b5 |

The selected style changes the seven chord definitions, not the physical grammar. Voice leading
chooses compact inversions automatically. A chord remains latched when the left hand moves away.

## Commands

| Gesture/control | Hand | Meaning | Guard |
|---|---|---|---|
| Pinch | Left | Cycle adaptive, color, pentatonic, blues, chord-tone lead modes | 400 ms |
| Fist | Left | Panic: stop every note and disarm | 120 ms |
| Swipe right/left | Left | Fallback next/previous progression chord | velocity + cooldown |
| Pinch edge | Right | Re-articulate current melody note | edge-triggered |
| Sustain button | UI | Toggle independent CC64 pedal | explicit control |
| Record / Play / Clear | UI | Capture and control the bounded performance loop | explicit control |

Fist and pinch are reserved; they are never chord shapes. Sustain is an explicit UI control to
avoid accidental pedal toggles during chord formation.

## Right hand: chord-relative melody and expression

| Dimension | Musical behavior |
|---|---|
| X position | Legato note from the active chord-relative palette |
| Movement speed | Vibrato depth |
| Y position / motion | Volume, expression, and attack energy |
| Z toward / away | Expression, brightness, and delay |
| Pinch amount | Reverb send |
| Motion + Y | Chorus send |

Adaptive mode selects a quality-aware scale: major to Ionian, minor to Aeolian, dominant to
Mixolydian, diminished to Locrian, and augmented to whole tone. Color mode uses Lydian, Dorian,
Altered, diminished, Locrian-natural-2, or Lydian-augmented colors. Every palette merges in the
active chord tones, preventing avoidable clashes on strong notes.

## Recognition and tracking rules

1. Reject observations below confidence threshold.
2. Require a stable hold for every discrete pose.
3. Emit once and require release before the same command can re-arm.
4. Route chord commands only from the left and melody/expression only from the right.
5. Release melody after 250 ms of right-hand loss while preserving the left chord.
6. Stop all notes after 1500 ms with no tracked hands.
7. Treat ordinary movement as `NO_GESTURE` in future ML datasets.
