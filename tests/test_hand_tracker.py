from pathlib import Path

import handmusic.tracking.hand_tracker as hand_tracker


def test_model_resolution_finds_checkout_model_from_another_working_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_repo = tmp_path / "fake-repo"
    fake_module = fake_repo / "src" / "handmusic" / "tracking" / "hand_tracker.py"
    model = fake_repo / "models" / "hand_landmarker.task"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"test model")
    monkeypatch.setattr(hand_tracker, "__file__", str(fake_module))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    resolved = hand_tracker.resolve_hand_model_path("models/hand_landmarker.task")

    assert resolved == model.resolve()


def test_tasks_timestamps_are_strictly_monotonic() -> None:
    tracker = hand_tracker.MediaPipeHandTracker.__new__(hand_tracker.MediaPipeHandTracker)
    tracker._last_timestamp_ms = None

    assert tracker._next_timestamp(100) == 100
    assert tracker._next_timestamp(100) == 101
    assert tracker._next_timestamp(99) == 102
    assert tracker._next_timestamp(110) == 110
