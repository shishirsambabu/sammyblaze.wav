from __future__ import annotations

from time import monotonic

from handmusic.gestures.features import extract_features
from handmusic.tracking.camera import frames
from handmusic.tracking.hand_tracker import MediaPipeHandTracker, TrackerConfig

from .recording import SessionRecorder


def record_camera_session(
    output_path: str,
    label: str,
    camera_index: int,
    hand_model: str,
    duration_seconds: float,
) -> int:
    """Record landmark features for one labeled session, never raw frames."""
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("Install the [vision] extra to record a camera session") from exc
    if duration_seconds <= 0.0:
        raise ValueError("duration_seconds must be positive")

    tracker = MediaPipeHandTracker(TrackerConfig(model_path=hand_model))
    start = monotonic()
    count = 0
    with SessionRecorder(output_path, metadata={"source": "camera", "label": label}) as recorder:
        try:
            for frame, timestamp_ms in frames(camera_index):
                for observation in tracker.process(frame, timestamp_ms):
                    count += int(recorder.record(extract_features(observation), label) is not None)
                cv2.putText(
                    frame,
                    f"Recording {label}: {count} samples | Esc stops",
                    (20, 32),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (50, 220, 50),
                    2,
                )
                cv2.imshow("SammyBlaze.wav recording", frame)
                if cv2.waitKey(1) & 0xFF == 27 or monotonic() - start >= duration_seconds:
                    break
        finally:
            tracker.close()
            cv2.destroyAllWindows()
    print(f"Recorded {count} feature samples to {output_path}")
    return count
