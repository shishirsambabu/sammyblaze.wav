# Computer vision subagent

Build local camera and hand-landmark adapters. Hide OpenCV/MediaPipe types behind `HandObservation`. Support up to two hands, timestamps, confidence, and clean shutdown. Keep optional dependencies lazy so dry-run and CI work without a camera.

Required handoff: hardware assumptions, tracking-loss behavior, overlay screenshots or logs, and deterministic tests for conversion/normalization.
