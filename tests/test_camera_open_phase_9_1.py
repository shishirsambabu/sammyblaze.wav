from __future__ import annotations

import sys
from collections.abc import Callable
from threading import Event, Lock, Thread
from types import SimpleNamespace
from typing import Any

import pytest

from handmusic.tracking import camera as camera_module


class FakeCapture:
    def __init__(
        self,
        *,
        opened: bool = True,
        first_frame: Any | None = None,
    ) -> None:
        self.opened = opened
        self.first_frame = first_frame
        self.released = Event()
        self.settings: list[tuple[int, int]] = []
        self.read_count = 0

    def isOpened(self) -> bool:
        return self.opened

    def set(self, prop: int, value: int) -> bool:
        self.settings.append((prop, value))
        return True

    def read(self) -> tuple[bool, Any | None]:
        self.read_count += 1
        if self.read_count == 1 and self.first_frame is not None:
            return True, self.first_frame
        return False, None

    def release(self) -> None:
        self.released.set()


def install_fake_cv2(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[[int, int], FakeCapture],
) -> Any:
    fake_cv2 = SimpleNamespace(
        CAP_DSHOW=100,
        CAP_MSMF=200,
        CAP_ANY=300,
        CAP_PROP_BUFFERSIZE=400,
        VideoCapture=factory,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    return fake_cv2


def wait_for_all_open_worker_slots() -> None:
    acquired = 0
    for _ in range(camera_module._MAX_OPEN_WORKERS):
        if camera_module._OPEN_WORKER_SLOTS.acquire(timeout=1.0):
            acquired += 1
    for _ in range(acquired):
        camera_module._OPEN_WORKER_SLOTS.release()
    assert acquired == camera_module._MAX_OPEN_WORKERS


def test_camera_open_falls_back_without_waiting_for_blocked_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dshow_gate = Event()
    dshow_entered = Event()
    dshow_capture = FakeCapture(first_frame="stale")
    msmf_capture = FakeCapture(first_frame="fresh")
    calls: list[int] = []

    def factory(_camera_index: int, backend: int) -> FakeCapture:
        calls.append(backend)
        if backend == 100:
            dshow_entered.set()
            dshow_gate.wait(timeout=2.0)
            return dshow_capture
        return msmf_capture

    install_fake_cv2(monkeypatch, factory)
    monkeypatch.setattr(camera_module, "platform", "win32")

    stream = camera_module.CameraStream(2, open_timeout_s=0.3)
    try:
        assert dshow_entered.is_set()
        assert stream.backend_name == "Media Foundation"
        assert calls == [100, 200]
        assert next(iter(stream))[0] == "fresh"
    finally:
        stream.close()
        dshow_gate.set()

    assert dshow_capture.released.wait(timeout=1.0)
    wait_for_all_open_worker_slots()


def test_camera_open_cancellation_interrupts_waiting_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_gate = Event()
    constructor_entered = Event()
    late_capture = FakeCapture(first_frame="late")
    stop_event = Event()

    def factory(_camera_index: int, _backend: int) -> FakeCapture:
        constructor_entered.set()
        constructor_gate.wait(timeout=2.0)
        return late_capture

    install_fake_cv2(monkeypatch, factory)
    monkeypatch.setattr(camera_module, "platform", "linux")

    def request_stop() -> None:
        assert constructor_entered.wait(timeout=1.0)
        stop_event.set()

    stopper = Thread(target=request_stop)
    stopper.start()
    try:
        with pytest.raises(camera_module.CameraOpenCancelled, match="open cancelled"):
            camera_module.CameraStream(
                0,
                stop_event=stop_event,
                open_timeout_s=1.0,
            )
    finally:
        constructor_gate.set()
        stopper.join(timeout=1.0)

    assert late_capture.released.wait(timeout=1.0)
    wait_for_all_open_worker_slots()


def test_camera_open_honours_pre_cancel_without_starting_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def factory(camera_index: int, backend: int) -> FakeCapture:
        calls.append((camera_index, backend))
        return FakeCapture(first_frame="unexpected")

    install_fake_cv2(monkeypatch, factory)
    stop_event = Event()
    stop_event.set()

    with pytest.raises(camera_module.CameraOpenCancelled):
        camera_module.CameraStream(4, stop_event=stop_event)

    assert calls == []


def test_frames_observes_external_stop_after_first_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = FakeCapture(first_frame="frame")
    install_fake_cv2(monkeypatch, lambda _index, _backend: capture)
    monkeypatch.setattr(camera_module, "platform", "linux")
    stop_event = Event()

    iterator = camera_module.frames(
        0,
        stop_event=stop_event,
        open_timeout_s=0.2,
    )
    assert next(iterator)[0] == "frame"

    stop_event.set()
    with pytest.raises(StopIteration):
        next(iterator)
    assert capture.released.wait(timeout=1.0)


def test_hanging_open_workers_are_globally_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_gate = Event()
    state_lock = Lock()
    active = 0
    max_active = 0
    call_count = 0

    def factory(_camera_index: int, _backend: int) -> FakeCapture:
        nonlocal active, call_count, max_active
        with state_lock:
            active += 1
            call_count += 1
            max_active = max(max_active, active)
        try:
            constructor_gate.wait(timeout=2.0)
            return FakeCapture(first_frame="late")
        finally:
            with state_lock:
                active -= 1

    install_fake_cv2(monkeypatch, factory)
    monkeypatch.setattr(camera_module, "platform", "linux")
    failures: list[Exception] = []

    def open_camera(index: int) -> None:
        try:
            camera_module.CameraStream(index, open_timeout_s=0.1)
        except Exception as exc:
            failures.append(exc)

    callers = [Thread(target=open_camera, args=(index,)) for index in range(8)]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join(timeout=1.0)

    assert all(not caller.is_alive() for caller in callers)
    assert len(failures) == len(callers)
    assert all(isinstance(exc, RuntimeError) for exc in failures)
    assert call_count <= camera_module._MAX_OPEN_WORKERS
    assert max_active <= camera_module._MAX_OPEN_WORKERS

    constructor_gate.set()
    wait_for_all_open_worker_slots()


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan")])
def test_camera_open_timeout_must_be_positive_and_finite(timeout: float) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        camera_module.CameraStream(open_timeout_s=timeout)
