# Phase 1 camera diagnostics

Install the vision extra, then start the diagnostics loop:

```powershell
python -m pip install -e ".[dev,vision,midi]"
python -m handmusic --camera 0 --output midi
```

The window displays the hand skeleton, handedness/confidence, gesture state, tracked-hand count, and rolling FPS. Press `Esc` to stop. The camera producer uses a one-item latest-frame queue so slow tracking cannot accumulate stale frames.

The deterministic test suite does not require a webcam, MediaPipe, MIDI device, or internet connection. Hardware smoke testing is intentionally separate from CI and should record camera model, lighting, FPS, and tracking-loss behavior in the Phase 1 handoff.
