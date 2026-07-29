import json

from handmusic.telemetry import PerformanceTelemetry, render_telemetry, save_telemetry


def test_telemetry_tracks_age_gestures_and_dropped_frames() -> None:
    telemetry = PerformanceTelemetry(expected_fps=30.0)
    telemetry.record_frame(0, received_at_ms=0)
    telemetry.record_frame(33, received_at_ms=33)
    telemetry.record_frame(200, received_at_ms=200)
    telemetry.record_hand()
    telemetry.record_gesture(170, processed_at_ms=200)

    snapshot = telemetry.snapshot()

    assert snapshot.frames_seen == 3
    assert snapshot.hands_seen == 1
    assert snapshot.gestures_seen == 1
    assert snapshot.dropped_frames == 4
    assert snapshot.mean_gesture_latency_ms == 30.0
    assert "Dropped frames: 4" in render_telemetry(snapshot)


def test_save_telemetry_is_valid_json(tmp_path) -> None:
    telemetry = PerformanceTelemetry()
    telemetry.record_frame(0, received_at_ms=5)
    destination = tmp_path / "session" / "telemetry.json"

    save_telemetry(destination, telemetry.snapshot())

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["frames_seen"] == 1
