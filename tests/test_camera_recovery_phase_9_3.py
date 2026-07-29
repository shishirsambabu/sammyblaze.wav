from __future__ import annotations

import sys
from collections import deque
from collections.abc import Callable, Iterable
from threading import Event, Lock, Thread
from time import monotonic, sleep
from types import SimpleNamespace
from typing import Any

import pytest

from handmusic.tracking import camera as camera_module


class ScriptedCapture:
    def __init__(
        self,
        responses: Iterable[tuple[bool, Any | None]] = (),
        *,
        opened: bool = True,
    ) -> None:
        self.opened = opened
        self.responses = deque(responses)
        self.released = Event()
        self.read_entered = Event()
        self._lock = Lock()
        self.release_count = 0
        self.read_count = 0

    def isOpened(self) -> bool:
        return self.opened

    def set(self, _prop: int, _value: int) -> bool:
        return True

    def read(self) -> tuple[bool, Any | None]:
        self.read_entered.set()
        with self._lock:
            self.read_count += 1
            if self.responses:
                return self.responses.popleft()
        self.released.wait(timeout=1.0)
        return False, None

    def release(self) -> None:
        with self._lock:
            self.release_count += 1
        self.released.set()


def install_fake_cv2(
    monkeypatch: pytest.MonkeyPatch,
    factory: Callable[[int, int], ScriptedCapture],
) -> None:
    fake_cv2 = SimpleNamespace(
        CAP_DSHOW=100,
        CAP_MSMF=200,
        CAP_ANY=300,
        CAP_PROP_BUFFERSIZE=400,
        VideoCapture=factory,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(camera_module, "platform", "linux")


def wait_until(predicate: Callable[[], bool], *, timeout: float = 1.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.005)
    raise AssertionError("condition was not reached before the test deadline")


def wait_for_all_open_worker_slots() -> None:
    acquired = 0
    for _ in range(camera_module._MAX_OPEN_WORKERS):
        if camera_module._OPEN_WORKER_SLOTS.acquire(timeout=1.0):
            acquired += 1
    for _ in range(acquired):
        camera_module._OPEN_WORKER_SLOTS.release()
    assert acquired == camera_module._MAX_OPEN_WORKERS


def test_transient_read_failures_resume_without_reopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = ScriptedCapture(
        [
            (True, "startup"),
            (False, None),
            (False, None),
            (True, "after-transient-failure"),
        ]
    )
    calls: list[int] = []

    def factory(_camera_index: int, backend: int) -> ScriptedCapture:
        calls.append(backend)
        return capture

    install_fake_cv2(monkeypatch, factory)
    stream = camera_module.CameraStream(
        0,
        open_timeout_s=0.1,
        recovery_timeout_s=0.2,
        read_failure_retries=2,
    )
    try:
        iterator = iter(stream)
        frame, _timestamp = next(iterator)
        if frame == "startup":
            frame, _timestamp = next(iterator)
        assert frame == "after-transient-failure"
        assert calls == [300]
        assert stream.generation == 0
        assert stream.terminal_error is None
    finally:
        stream.close()

    assert not stream.worker_alive
    assert capture.release_count == 1


def test_failed_capture_reopens_and_publishes_new_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ScriptedCapture([(True, "startup"), (False, None)])
    recovered = ScriptedCapture([(True, "recovered")])
    captures = deque([original, recovered])

    install_fake_cv2(monkeypatch, lambda _index, _backend: captures.popleft())
    stream = camera_module.CameraStream(
        0,
        open_timeout_s=0.1,
        recovery_timeout_s=0.3,
        recovery_attempts=2,
        read_failure_retries=0,
    )
    try:
        wait_until(lambda: stream.generation == 1)
        frame, _timestamp = next(iter(stream))
        assert frame == "recovered"
        assert stream.backend_name == "automatic"
        assert stream.terminal_error is None
        assert original.release_count == 1
    finally:
        stream.close()

    assert not stream.worker_alive
    assert recovered.release_count == 1


def test_permanent_failure_is_bounded_and_wakes_consumer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = ScriptedCapture([(True, "startup"), (False, None)])
    failed_reopens = [ScriptedCapture(opened=False) for _ in range(2)]
    captures = deque([initial, *failed_reopens])

    install_fake_cv2(monkeypatch, lambda _index, _backend: captures.popleft())
    started = monotonic()
    stream = camera_module.CameraStream(
        0,
        open_timeout_s=0.05,
        recovery_timeout_s=0.2,
        recovery_attempts=2,
        read_failure_retries=0,
    )
    iterator = iter(stream)
    try:
        first, _timestamp = next(iterator)
        assert first == "startup"
        consumer_errors: list[BaseException] = []

        def consume_terminal_state() -> None:
            try:
                next(iterator)
            except BaseException as exc:
                consumer_errors.append(exc)

        consumer = Thread(target=consume_terminal_state)
        consumer.start()
        consumer.join(timeout=0.5)
        assert not consumer.is_alive()
        assert len(consumer_errors) == 1
        assert isinstance(consumer_errors[0], camera_module.CameraRecoveryExhausted)
        assert "bounded recovery" in str(consumer_errors[0])
        assert monotonic() - started < 0.5
        assert isinstance(stream.terminal_error, camera_module.CameraRecoveryExhausted)
        assert stream.generation == 0
        wait_until(lambda: not stream.worker_alive)
    finally:
        stream.close()

    assert initial.release_count == 1
    assert all(capture.release_count == 1 for capture in failed_reopens)


def test_external_stop_interrupts_reopen_and_releases_late_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = ScriptedCapture([(True, "startup"), (False, None)])
    late = ScriptedCapture([(True, "late")])
    reopen_entered = Event()
    reopen_gate = Event()
    stop_event = Event()
    call_count = 0

    def factory(_camera_index: int, _backend: int) -> ScriptedCapture:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return initial
        reopen_entered.set()
        reopen_gate.wait(timeout=1.0)
        return late

    install_fake_cv2(monkeypatch, factory)
    stream = camera_module.CameraStream(
        0,
        stop_event=stop_event,
        open_timeout_s=0.5,
        recovery_timeout_s=0.8,
        recovery_attempts=2,
        read_failure_retries=0,
    )
    try:
        assert reopen_entered.wait(timeout=0.5)
        stop_event.set()
        wait_until(lambda: not stream.worker_alive)
        assert stream.terminal_error is None
        assert stream.generation == 0
    finally:
        reopen_gate.set()
        stream.close()

    assert initial.release_count == 1
    assert late.released.wait(timeout=1.0)
    assert late.release_count == 1
    wait_for_all_open_worker_slots()


def test_concurrent_close_during_reopen_has_no_capture_or_worker_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = ScriptedCapture([(True, "startup"), (False, None)])
    late = ScriptedCapture([(True, "late")])
    reopen_entered = Event()
    reopen_gate = Event()
    call_count = 0

    def factory(_camera_index: int, _backend: int) -> ScriptedCapture:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return initial
        reopen_entered.set()
        reopen_gate.wait(timeout=1.0)
        return late

    install_fake_cv2(monkeypatch, factory)
    stream = camera_module.CameraStream(
        0,
        open_timeout_s=0.5,
        recovery_timeout_s=0.8,
        recovery_attempts=2,
        read_failure_retries=0,
    )
    assert reopen_entered.wait(timeout=0.5)

    closers = [Thread(target=stream.close) for _ in range(2)]
    for closer in closers:
        closer.start()
    for closer in closers:
        closer.join(timeout=1.0)
    reopen_gate.set()

    assert all(not closer.is_alive() for closer in closers)
    assert not stream.worker_alive
    assert stream.terminal_error is None
    assert stream.generation == 0
    assert initial.release_count == 1
    assert late.released.wait(timeout=1.0)
    assert late.release_count == 1
    wait_for_all_open_worker_slots()


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("recovery_timeout_s", 0.0, "positive finite"),
        ("recovery_timeout_s", float("inf"), "positive finite"),
        ("recovery_attempts", 0, "positive integer"),
        ("recovery_attempts", True, "positive integer"),
        ("read_failure_retries", -1, "non-negative integer"),
        ("read_failure_retries", True, "non-negative integer"),
    ],
)
def test_recovery_configuration_is_bounded_and_validated(
    keyword: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        camera_module.CameraStream(**{keyword: value})
