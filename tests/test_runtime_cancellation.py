from __future__ import annotations

from threading import Event

import handmusic.app as app_module
from handmusic.app import default_runtime, run_camera


def test_run_camera_returns_before_loading_optional_runtime_when_cancelled(
    monkeypatch,
) -> None:
    stop_event = Event()
    stop_event.set()
    tracker_constructed = False

    class UnexpectedTracker:
        def __init__(self, _config) -> None:
            nonlocal tracker_constructed
            tracker_constructed = True

    monkeypatch.setattr(app_module, "MediaPipeHandTracker", UnexpectedTracker)
    runtime, _output = default_runtime()

    run_camera(runtime, 0, stop_event=stop_event, display=False)

    assert tracker_constructed is False


def test_run_camera_passes_cancellation_to_camera_stream(monkeypatch) -> None:
    stop_event = Event()
    tracker_closed = False
    received_stop_event: Event | None = None

    class FakeTracker:
        def __init__(self, _config) -> None:
            pass

        def process(self, _frame, _timestamp_ms: int) -> list[object]:
            return []

        def close(self) -> None:
            nonlocal tracker_closed
            tracker_closed = True

    def fake_frames(
        _camera_index: int,
        *,
        stop_event: Event | None = None,
    ):
        nonlocal received_stop_event
        received_stop_event = stop_event
        stop_event.set()
        if False:
            yield object(), 0

    monkeypatch.setattr(app_module, "MediaPipeHandTracker", FakeTracker)
    monkeypatch.setattr(app_module, "frames", fake_frames)
    runtime, _output = default_runtime()

    run_camera(runtime, 0, stop_event=stop_event, display=False)

    assert received_stop_event is stop_event
    assert tracker_closed is True


def test_run_camera_passes_camera_health_observer(monkeypatch) -> None:
    stop_event = Event()
    received_callback = None

    class FakeTracker:
        def __init__(self, _config) -> None:
            pass

        def close(self) -> None:
            pass

    def health_observer(_snapshot: object) -> None:
        pass

    def fake_frames(
        _camera_index: int,
        *,
        stop_event: Event | None = None,
        health_callback=None,
    ):
        nonlocal received_callback
        received_callback = health_callback
        assert stop_event is not None
        stop_event.set()
        if False:
            yield object(), 0

    monkeypatch.setattr(app_module, "MediaPipeHandTracker", FakeTracker)
    monkeypatch.setattr(app_module, "frames", fake_frames)
    runtime, _output = default_runtime()

    run_camera(
        runtime,
        0,
        stop_event=stop_event,
        camera_health_callback=health_observer,
        display=False,
    )

    assert received_callback is health_observer
