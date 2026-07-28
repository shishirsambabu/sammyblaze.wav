# Gesture language v1

The performer should be able to return to a neutral open/relaxed hand between discrete commands. Static poses are never mapped directly to repeated notes.

| Gesture | Hand | Semantics | Guard |
|---|---|---|---|
| Open palm | Left or primary | Arm and play current chord | Held 500 ms |
| Fist | Any | Stop all notes and disarm | Confidence > 0.70 |
| Swipe right | Left or primary | Next progression slot | Velocity and cooldown |
| Swipe left | Left or primary | Previous progression slot | Velocity and cooldown |
| Pinch | Right or primary | Toggle arpeggiator | Held 180 ms |
| Vertical movement | Right | Expression/volume | Smoothed continuously |
| Horizontal movement | Right | Pan/filter target | Smoothed continuously |

## Recognition rules

1. Reject observations below confidence threshold.
2. Require a stable hold for static commands.
3. Emit a discrete event once, then enter cooldown.
4. Do not re-arm the same gesture until neutral is observed.
5. Treat ordinary movement as `NO_GESTURE` in future ML datasets.
