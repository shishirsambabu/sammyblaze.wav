from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import replace
from pathlib import Path
from threading import Condition

import pytest

from handmusic.reliability.camera_soak import (
    CameraSoakConfig,
    atomic_write_json,
    main,
    run_camera_soak,
)
from handmusic.tracking.camera import CameraHealthSnapshot, CameraRecoveryExhausted


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.stream: _FakeCameraStream | None = None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration
        if self.stream is not None:
            self.stream.advance(self.now)


class _FakeCameraStream:
    def __init__(
        self,
        camera_index: int,
        *,
        clock: _FakeClock,
        recovery_timeout_s: float,
        health_callback: object,
        advance_generation: bool = True,
        emit_post_recovery_frame: bool = True,
        terminal_on_recovery: bool = False,
        iterator_error: BaseException | None = None,
    ) -> None:
        del recovery_timeout_s
        self.camera_index = camera_index
        self.clock = clock
        self.clock.stream = self
        self.health_callback = health_callback
        self.advance_generation = advance_generation
        self.emit_post_recovery_frame = emit_post_recovery_frame
        self.terminal_on_recovery = terminal_on_recovery
        self.iterator_error = iterator_error
        self.backend_name: str | None = "Fake DirectShow"
        self._generation = 0
        self._terminal_error: BaseException | None = None
        self._worker_alive = True
        self._recovery_requested = False
        self._suppress_frames = False
        self._closed = False
        self._condition = Condition()
        self._frames: deque[tuple[object, int]] = deque()
        self._produced = 0
        self._consumed = 0
        self.close_count = 0
        self.request_count = 0
        self._publish("opening")
        self._queue_frame(0)
        self._publish("running")

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def terminal_error(self) -> BaseException | None:
        return self._terminal_error

    @property
    def worker_alive(self) -> bool:
        return self._worker_alive

    def request_recovery(self) -> None:
        self.request_count += 1
        self._recovery_requested = True

    def advance(self, now: float) -> None:
        if self._closed or not self._worker_alive:
            return
        if self._suppress_frames:
            return
        if self._recovery_requested:
            self._recovery_requested = False
            self._publish("recovering")
            if self.terminal_on_recovery:
                self._terminal_error = CameraRecoveryExhausted("injected terminal error")
                self._worker_alive = False
                self._publish("failed", str(self._terminal_error))
                with self._condition:
                    self._condition.notify_all()
                return
            if self.advance_generation:
                self._generation += 1
            self._publish("recovered")
            if not self.emit_post_recovery_frame:
                self._suppress_frames = True
                return
        self._queue_frame(math.ceil(now * 1_000.0) + 1)
        self._wait_for_consumer()

    def __iter__(self) -> object:
        while True:
            with self._condition:
                while not self._frames and not self._closed and self._worker_alive:
                    self._condition.wait()
                if self._frames:
                    frame = self._frames.popleft()
                    self._consumed += 1
                    self._condition.notify_all()
                elif self._terminal_error is not None:
                    raise self._terminal_error
                else:
                    return
            yield frame
            if self.iterator_error is not None:
                error, self.iterator_error = self.iterator_error, None
                raise error

    def close(self) -> None:
        self.close_count += 1
        self._closed = True
        self._worker_alive = False
        self._publish("stopped")
        with self._condition:
            self._condition.notify_all()

    def _queue_frame(self, captured_at_ms: int) -> None:
        with self._condition:
            self._frames.append((object(), captured_at_ms))
            self._produced += 1
            self._condition.notify_all()

    def _wait_for_consumer(self) -> None:
        with self._condition:
            self._condition.wait_for(
                lambda: self._consumed >= self._produced or self._closed,
                timeout=0.25,
            )

    def _publish(self, state: str, detail: str | None = None) -> None:
        callback = self.health_callback
        assert callable(callback)
        callback(
            CameraHealthSnapshot(
                camera_index=self.camera_index,
                state=state,
                generation=self._generation,
                backend=self.backend_name,
                detail=detail,
            )
        )


def _run_fake(
    config: CameraSoakConfig | None = None,
    **stream_options: object,
) -> tuple[dict[str, object], _FakeCameraStream]:
    clock = _FakeClock()
    created: list[_FakeCameraStream] = []

    def factory(camera_index: int, **kwargs: object) -> _FakeCameraStream:
        stream = _FakeCameraStream(
            camera_index,
            clock=clock,
            **stream_options,
            **kwargs,
        )
        created.append(stream)
        return stream

    report = run_camera_soak(
        config
        or CameraSoakConfig(
            duration_seconds=0.2,
            forced_recovery_count=2,
            minimum_fps=1.0,
            max_recovery_seconds=0.05,
        ),
        stream_factory=factory,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return report, created[0]


def test_phase9_4_camera_soak_proves_every_forced_recovery() -> None:
    report, stream = _run_fake()

    assert report["result"] == {"passed": True, "reasons": []}
    assert report["recoveries"]["requested"] == 2
    assert report["recoveries"]["proven"] == 2
    assert stream.request_count == 2
    assert stream.close_count == 1
    attempts = report["recoveries"]["attempts"]
    assert [attempt["observed_generation"] for attempt in attempts] == [1, 2]
    assert all(attempt["first_frame_number"] is not None for attempt in attempts)
    assert all(attempt["latency_seconds"] <= 0.05 for attempt in attempts)
    assert report["camera"]["initial_backend"] == "Fake DirectShow"
    assert report["camera"]["final_generation"] == 2
    states = [snapshot["state"] for snapshot in report["lifecycle_snapshots"]]
    assert states.count("recovered") == 2
    assert report["test_scope"]["diagnostic_close_reopen_tested"] is True
    assert report["test_scope"]["physical_unplug_replug_tested"] is False
    assert report["test_scope"]["physical_unplug_replug_proven"] is False


def test_phase9_4_camera_soak_fails_when_generation_does_not_advance() -> None:
    report, stream = _run_fake(advance_generation=False)

    assert report["result"]["passed"] is False
    codes = {reason["code"] for reason in report["result"]["reasons"]}
    assert "recovery_generation_not_advanced" in codes
    assert report["recoveries"]["proven"] == 0
    assert stream.close_count == 1


def test_phase9_4_camera_soak_fails_without_frame_after_new_generation() -> None:
    config = CameraSoakConfig(
        duration_seconds=0.12,
        forced_recovery_count=1,
        minimum_fps=1.0,
        max_recovery_seconds=0.03,
    )
    report, stream = _run_fake(
        config,
        emit_post_recovery_frame=False,
    )

    assert report["result"]["passed"] is False
    codes = {reason["code"] for reason in report["result"]["reasons"]}
    assert "missing_post_recovery_frame" in codes
    assert report["camera"]["final_generation"] == 1
    assert stream.close_count == 1


def test_phase9_4_camera_soak_records_terminal_error_and_closes() -> None:
    report, stream = _run_fake(terminal_on_recovery=True)

    assert report["result"]["passed"] is False
    codes = {reason["code"] for reason in report["result"]["reasons"]}
    assert {"terminal_error", "recovery_terminal_error"} <= codes
    assert "injected terminal error" in report["camera"]["terminal_error"]
    assert stream.close_count == 1
    assert report["camera"]["worker_alive_after_close"] is False


def test_phase9_4_camera_soak_closes_after_consumer_exception() -> None:
    report, stream = _run_fake(iterator_error=RuntimeError("injected read failure"))

    assert report["result"]["passed"] is False
    assert report["result"]["reasons"][0]["code"] == "run_error"
    assert "injected read failure" in report["result"]["reasons"][0]["detail"]
    assert stream.close_count == 1
    assert report["camera"]["worker_alive_after_close"] is False


def test_phase9_4_camera_soak_atomic_json_is_stable_and_leaves_no_temp(
    tmp_path: Path,
) -> None:
    report, _stream = _run_fake()
    destination = tmp_path / "nested" / "camera-soak.json"

    atomic_write_json(destination, report)
    first = destination.read_bytes()
    atomic_write_json(destination, report)

    assert destination.read_bytes() == first
    assert json.loads(first) == report
    assert not list(destination.parent.glob("*.tmp"))
    assert b'"camera"' < b'"configuration"'


@pytest.mark.parametrize(
    "arguments",
    [
        ["--camera", "-1"],
        ["--camera", "65"],
        ["--duration", "0"],
        ["--duration", "nan"],
        ["--forced-recoveries", "-1"],
        ["--minimum-fps", "0"],
        ["--minimum-fps", "inf"],
        ["--max-recovery-seconds", "0"],
        ["--max-recovery-seconds", "nan"],
    ],
)
def test_phase9_4_camera_soak_cli_rejects_invalid_arguments(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"camera_index": True},
        {"camera_index": 65},
        {"duration_seconds": 0},
        {"duration_seconds": float("inf")},
        {"forced_recovery_count": True},
        {"forced_recovery_count": -1},
        {"minimum_fps": 0},
        {"max_recovery_seconds": float("nan")},
    ],
)
def test_phase9_4_camera_soak_config_rejects_invalid_values(
    changes: dict[str, object],
) -> None:
    base = CameraSoakConfig()

    with pytest.raises(ValueError):
        replace(base, **changes)
