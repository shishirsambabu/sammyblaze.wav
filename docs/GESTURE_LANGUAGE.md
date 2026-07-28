# Gesture language v1

The performer should be able to return to a neutral open/relaxed hand between discrete commands. Static poses are never mapped directly to repeated notes.

| Gesture | Hand | Semantics | Guard |
|---|---|---|---|
| Open palm | Left | Arm and latch current voiced chord | Held 500 ms |
| Fist | Left | Stop all notes and disarm | Held 120 ms |
| Swipe right | Left | Next progression slot | Velocity and cooldown |
| Swipe left | Left | Previous progression slot | Velocity and cooldown |
| Pinch | Left | Cycle performance mode | Held 180 ms |
| Thumb only | Left | Toggle independent sustain pedal (MIDI CC64) | Held 220 ms |
| Two fingers | Left | Toggle arpeggiator flag | Held 180 ms |
| Horizontal movement | Right | Play stable legato scale note and pan | Hysteresis + smoothing |
| Downward movement | Right | Add velocity to the next note attack | Motion bounded |
| Vertical position | Right | Volume and expression | Smoothed continuously |
| Pinch edge | Right | Re-articulate current note | Edge-triggered |
| Pinch / depth | Right | Reverb, delay, and chorus sends | Smoothed continuously |

## Recognition rules

1. Reject observations below confidence threshold.
2. Require a stable hold for static commands.
3. Emit a discrete event once, then enter cooldown.
4. Do not re-arm the same gesture until neutral is observed.
5. Route chord commands only from the left hand and scale/expression controls only from the right.
6. Treat ordinary movement as `NO_GESTURE` in future ML datasets.
