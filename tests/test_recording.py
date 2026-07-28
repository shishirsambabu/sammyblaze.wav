from pathlib import Path

from handmusic.common.models import GestureFeatures
from handmusic.ml.recording import (
    FEATURE_NAMES,
    GestureSample,
    SessionRecorder,
    load_samples,
    split_by_session,
)


def feature(timestamp: int, session_hand: str = "left") -> GestureFeatures:
    return GestureFeatures(
        session_hand,
        (True, False, False, False, False),
        0.4,
        3.0,
        0.5,
        0.4,
        0.1,
        0.0,
        0.0,
        0.9,
        timestamp,
    )


def test_jsonl_recording_round_trips_without_frames(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    with SessionRecorder(path, session_id="session-a") as recorder:
        recorder.record(feature(1), "no_gesture")
    samples = load_samples(path)
    assert len(samples) == 1
    assert samples[0].label == "no_gesture"
    assert len(samples[0].values) == len(FEATURE_NAMES)


def test_split_by_session_never_leaks_session_ids() -> None:
    samples = [
        GestureSample("a", 1, "no_gesture", "left", (0.0,) * 13, {}),
        GestureSample("b", 1, "swipe_right", "left", (0.0,) * 13, {}),
        GestureSample("c", 1, "swipe_left", "left", (0.0,) * 13, {}),
        GestureSample("d", 1, "fist", "left", (0.0,) * 13, {}),
    ]
    splits = split_by_session(samples, seed=7)
    ids = {name: {sample.session_id for sample in values} for name, values in splits.items()}
    assert ids["train"].isdisjoint(ids["validation"])
    assert ids["train"].isdisjoint(ids["test"])
    assert ids["validation"].isdisjoint(ids["test"])
