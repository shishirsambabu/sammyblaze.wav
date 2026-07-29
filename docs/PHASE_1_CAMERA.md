# Phase 1 camera diagnostics

Install the vision extra, then start the diagnostics loop:

```powershell
python -m pip install -e ".[dev,vision]"
Invoke-WebRequest -Uri "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" -OutFile "models/hand_landmarker.task"
python -m handmusic --camera 0 --output null
```

For a bounded hardware smoke test, add `--max-frames 1` so the command exits after the first captured frame.

The window displays the hand skeleton, handedness/confidence, gesture state, tracked-hand count, and rolling FPS. Press `Esc` to stop. The camera producer uses a one-item latest-frame queue so slow tracking cannot accumulate stale frames.

Use `--hand-model path/to/hand_landmarker.task` to select another model. Use `--output midi` after installing `.[midi-native]` and configuring a MIDI destination. The deterministic test suite does not require a webcam, MediaPipe, MIDI device, or internet connection. Hardware smoke testing is intentionally separate from CI and should record camera model, lighting, FPS, and tracking-loss behavior in the Phase 1 handoff.

If Windows reports `WinError 4551`, its application-control policy is blocking MediaPipe's native shared library; allow that library or use a supported Python/Windows environment.
