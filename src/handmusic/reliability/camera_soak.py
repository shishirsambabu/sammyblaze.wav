"""Bounded camera reliability soak with forced-recovery evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Final, Protocol

from handmusic.tracking.camera import CameraHealthSnapshot, CameraStream

REPORT_SCHEMA: Final = "sammyblaze.camera-soak"
REPORT_SCHEMA_VERSION: Final = 1
DEFAULT_DURATION_SECONDS: Final = 60.0
DEFAULT_FORCED_RECOVERIES: Final = 3
DEFAULT_MINIMUM_FPS: Final = 15.0
DEFAULT_MAX_RECOVERY_SECONDS: Final = 3.0
_POLL_INTERVAL_SECONDS: Final = 0.01
_CONSUMER_JOIN_SECONDS: Final = 1.0


class _CameraStreamLike(Protocol):
    backend_name: str | None

    @property
    def generation(self) -> int: ...

    @property
    def terminal_error(self) -> BaseException | None: ...

    @property
    def worker_alive(self) -> bool: ...

    def __iter__(self) -> Iterator[tuple[Any, int]]: ...

    def request_recovery(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CameraSoakConfig:
    """Validated configuration for one real-camera reliability run."""

    camera_index: int = 0
    duration_seconds: float = DEFAULT_DURATION_SECONDS
    forced_recovery_count: int = DEFAULT_FORCED_RECOVERIES
    minimum_fps: float = DEFAULT_MINIMUM_FPS
    max_recovery_seconds: float = DEFAULT_MAX_RECOVERY_SECONDS

    def __post_init__(self) -> None:
        _validate_int(
            "camera_index",
            self.camera_index,
            minimum=0,
            maximum=64,
        )
        _validate_float(
            "duration_seconds",
            self.duration_seconds,
            minimum=0.01,
            maximum=86_400.0,
        )
        _validate_int(
            "forced_recovery_count",
            self.forced_recovery_count,
            minimum=0,
            maximum=1_000,
        )
        _validate_float(
            "minimum_fps",
            self.minimum_fps,
            minimum=0.01,
            maximum=1_000.0,
        )
        _validate_float(
            "max_recovery_seconds",
            self.max_recovery_seconds,
            minimum=0.01,
            maximum=300.0,
        )


@dataclass(frozen=True, slots=True)
class _FrameObservation:
    frame_number: int
    observed_at: float
    captured_at_ms: int
    generation: int
    backend: str | None


class _FrameMonitor:
    """Thread-safe, bounded observation state for the newest-frame consumer."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._frame_count = 0
        self._latest: _FrameObservation | None = None
        self._consumer_error: str | None = None
        self._finished = False

    def observe(
        self,
        *,
        observed_at: float,
        captured_at_ms: int,
        generation: int,
        backend: str | None,
    ) -> None:
        with self._lock:
            self._frame_count += 1
            self._latest = _FrameObservation(
                frame_number=self._frame_count,
                observed_at=observed_at,
                captured_at_ms=captured_at_ms,
                generation=generation,
                backend=backend,
            )

    def fail(self, error: BaseException) -> None:
        with self._lock:
            self._consumer_error = _describe_error(error)

    def finish(self) -> None:
        with self._lock:
            self._finished = True

    def snapshot(
        self,
    ) -> tuple[int, _FrameObservation | None, str | None, bool]:
        with self._lock:
            return (
                self._frame_count,
                self._latest,
                self._consumer_error,
                self._finished,
            )


@dataclass(slots=True)
class _RecoveryAttempt:
    sequence: int
    requested_at: float
    requested_at_ms: int
    baseline_generation: int
    baseline_frame_count: int
    deadline: float
    passed: bool | None = None
    failure_code: str | None = None
    failure_detail: str | None = None
    observed_generation: int | None = None
    first_frame_number: int | None = None
    first_frame_captured_at_ms: int | None = None
    latency_seconds: float | None = None
    backend: str | None = None


def run_camera_soak(
    config: CameraSoakConfig,
    *,
    stream_factory: Callable[..., _CameraStreamLike] = CameraStream,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Exercise the real latest-frame stream and return a machine-readable report."""

    if not isinstance(config, CameraSoakConfig):
        raise TypeError("config must be a CameraSoakConfig")

    invocation_started = monotonic()
    lifecycle_snapshots: list[dict[str, object]] = []
    lifecycle_lock = Lock()
    stream: _CameraStreamLike | None = None
    consumer: Thread | None = None
    monitor = _FrameMonitor()
    recoveries: list[_RecoveryAttempt] = []
    run_error: str | None = None
    cleanup_errors: list[str] = []
    terminal_error: str | None = None
    initial_backend: str | None = None
    initial_generation: int | None = None
    worker_alive_before_close: bool | None = None
    worker_alive_after_close: bool | None = None
    exercise_started: float | None = None
    exercise_ended: float | None = None

    def record_health(snapshot: CameraHealthSnapshot) -> None:
        with lifecycle_lock:
            lifecycle_snapshots.append(
                {
                    "at_seconds": _rounded(monotonic() - invocation_started),
                    "camera_index": snapshot.camera_index,
                    "state": snapshot.state,
                    "generation": snapshot.generation,
                    "backend": snapshot.backend,
                    "detail": snapshot.detail,
                }
            )

    try:
        stream = stream_factory(
            config.camera_index,
            recovery_timeout_s=config.max_recovery_seconds,
            health_callback=record_health,
        )
        initial_backend = stream.backend_name
        initial_generation = stream.generation
        exercise_started = monotonic()
        exercise_deadline = exercise_started + config.duration_seconds
        recovery_schedule = [
            exercise_started
            + (config.duration_seconds * sequence / (config.forced_recovery_count + 1))
            for sequence in range(1, config.forced_recovery_count + 1)
        ]
        consumer = Thread(
            target=_consume_frames,
            kwargs={
                "stream": stream,
                "monitor": monitor,
                "monotonic": monotonic,
            },
            name="camera-soak-consumer",
            daemon=True,
        )
        consumer.start()

        next_recovery = 0
        pending: _RecoveryAttempt | None = None
        while True:
            now = monotonic()
            frame_count, latest, consumer_error, consumer_finished = monitor.snapshot()
            current_terminal = stream.terminal_error
            if current_terminal is not None:
                terminal_error = _describe_error(current_terminal)
                if pending is not None:
                    _fail_recovery(
                        pending,
                        code="recovery_terminal_error",
                        detail=terminal_error,
                        generation=stream.generation,
                        backend=stream.backend_name,
                    )
                    pending = None
                exercise_ended = now
                break
            if consumer_error is not None:
                run_error = f"camera consumer failed: {consumer_error}"
                exercise_ended = now
                break
            if consumer_finished and not stream.worker_alive and now < exercise_deadline:
                run_error = "camera stream ended before the configured duration"
                exercise_ended = now
                break

            if pending is not None:
                qualifying = _qualifying_recovery_frame(pending, latest)
                if qualifying is not None and qualifying.observed_at <= pending.deadline:
                    _pass_recovery(
                        pending,
                        observation=qualifying,
                    )
                    pending = None
                elif now >= pending.deadline:
                    generation = stream.generation
                    if generation <= pending.baseline_generation:
                        code = "recovery_generation_not_advanced"
                        detail = (
                            f"generation remained {generation} for "
                            f"{config.max_recovery_seconds:g} seconds"
                        )
                    else:
                        code = "missing_post_recovery_frame"
                        detail = (
                            f"generation advanced to {generation}, but no newer frame "
                            "was consumed before the recovery deadline"
                        )
                    _fail_recovery(
                        pending,
                        code=code,
                        detail=detail,
                        generation=generation,
                        backend=stream.backend_name,
                    )
                    pending = None

            if (
                pending is None
                and next_recovery < len(recovery_schedule)
                and now >= recovery_schedule[next_recovery]
            ):
                pending = _RecoveryAttempt(
                    sequence=next_recovery + 1,
                    requested_at=now,
                    requested_at_ms=math.ceil(now * 1_000.0),
                    baseline_generation=stream.generation,
                    baseline_frame_count=frame_count,
                    deadline=now + config.max_recovery_seconds,
                    backend=stream.backend_name,
                )
                recoveries.append(pending)
                next_recovery += 1
                stream.request_recovery()

            if now >= exercise_deadline:
                if pending is not None:
                    generation = stream.generation
                    code = (
                        "recovery_generation_not_advanced"
                        if generation <= pending.baseline_generation
                        else "missing_post_recovery_frame"
                    )
                    _fail_recovery(
                        pending,
                        code=code,
                        detail="configured soak duration ended before recovery proof",
                        generation=generation,
                        backend=stream.backend_name,
                    )
                exercise_ended = now
                break

            wake_at = min(exercise_deadline, now + _POLL_INTERVAL_SECONDS)
            if pending is not None:
                wake_at = min(wake_at, pending.deadline)
            elif next_recovery < len(recovery_schedule):
                wake_at = min(wake_at, recovery_schedule[next_recovery])
            sleep(max(0.000_001, wake_at - now))
    except BaseException as exc:
        run_error = _describe_error(exc)
        exercise_ended = monotonic()
    finally:
        if stream is not None:
            try:
                current_terminal = stream.terminal_error
                if current_terminal is not None:
                    terminal_error = _describe_error(current_terminal)
            except BaseException as exc:
                cleanup_errors.append(f"terminal_error: {_describe_error(exc)}")
            try:
                worker_alive_before_close = stream.worker_alive
            except BaseException as exc:
                cleanup_errors.append(f"worker_before_close: {_describe_error(exc)}")
            try:
                stream.close()
            except BaseException as exc:
                cleanup_errors.append(f"close: {_describe_error(exc)}")
            if consumer is not None:
                consumer.join(timeout=_CONSUMER_JOIN_SECONDS)
                if consumer.is_alive():
                    cleanup_errors.append(
                        "consumer_join: camera consumer remained alive after close"
                    )
            try:
                worker_alive_after_close = stream.worker_alive
            except BaseException as exc:
                cleanup_errors.append(f"worker_after_close: {_describe_error(exc)}")

    if exercise_started is None:
        observed_duration = 0.0
    else:
        ended = exercise_ended if exercise_ended is not None else monotonic()
        observed_duration = max(0.0, ended - exercise_started)
    frame_count, latest, consumer_error, _consumer_finished = monitor.snapshot()
    if consumer_error is not None and run_error is None:
        run_error = f"camera consumer failed: {consumer_error}"
    final_generation = _safe_stream_value(stream, "generation")
    final_backend = _safe_stream_value(stream, "backend_name")
    reasons = _gate_reasons(
        config,
        frame_count=frame_count,
        observed_duration=observed_duration,
        recoveries=recoveries,
        lifecycle_snapshots=lifecycle_snapshots,
        initial_backend=initial_backend,
        run_error=run_error,
        terminal_error=terminal_error,
        cleanup_errors=cleanup_errors,
        worker_alive_before_close=worker_alive_before_close,
        worker_alive_after_close=worker_alive_after_close,
    )
    return _build_report(
        config,
        invocation_started=invocation_started,
        exercise_started=exercise_started,
        observed_duration=observed_duration,
        frame_count=frame_count,
        latest=latest,
        initial_backend=initial_backend,
        final_backend=final_backend,
        initial_generation=initial_generation,
        final_generation=final_generation,
        lifecycle_snapshots=lifecycle_snapshots,
        recoveries=recoveries,
        terminal_error=terminal_error,
        worker_alive_before_close=worker_alive_before_close,
        worker_alive_after_close=worker_alive_after_close,
        reasons=reasons,
    )


def atomic_write_json(path: str | os.PathLike[str], report: dict[str, object]) -> None:
    """Durably replace a JSON report without exposing a partial destination."""

    destination = Path(path)
    if not destination.name:
        raise ValueError("output JSON path must include a file name")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                report,
                temporary,
                ensure_ascii=True,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Soak SammyBlaze camera capture and request diagnostic close/reopen cycles."
        ),
    )
    parser.add_argument(
        "--camera",
        "--camera-index",
        dest="camera_index",
        type=_camera_index,
        default=0,
        help="OpenCV camera index (0-64)",
    )
    parser.add_argument(
        "--duration",
        type=_duration,
        default=DEFAULT_DURATION_SECONDS,
        help="exercise duration in seconds (0.01-86400)",
    )
    parser.add_argument(
        "--forced-recoveries",
        type=_forced_recoveries,
        default=DEFAULT_FORCED_RECOVERIES,
        help="diagnostic close/reopen cycles to request (0-1000)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("sammyblaze-camera-soak.json"),
        help="destination for the atomic machine-readable report",
    )
    parser.add_argument(
        "--minimum-fps",
        type=_minimum_fps,
        default=DEFAULT_MINIMUM_FPS,
        help="minimum accepted consumed-frame rate (0.01-1000)",
    )
    parser.add_argument(
        "--max-recovery-seconds",
        type=_max_recovery_seconds,
        default=DEFAULT_MAX_RECOVERY_SECONDS,
        help="maximum accepted latency for each forced recovery (0.01-300)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        config = CameraSoakConfig(
            camera_index=arguments.camera_index,
            duration_seconds=arguments.duration,
            forced_recovery_count=arguments.forced_recoveries,
            minimum_fps=arguments.minimum_fps,
            max_recovery_seconds=arguments.max_recovery_seconds,
        )
        report = run_camera_soak(config)
        atomic_write_json(arguments.output_json, report)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    print(json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True))
    result = report["result"]
    assert isinstance(result, dict)
    return 0 if result["passed"] else 1


def _consume_frames(
    *,
    stream: _CameraStreamLike,
    monitor: _FrameMonitor,
    monotonic: Callable[[], float],
) -> None:
    try:
        for _frame, captured_at_ms in stream:
            monitor.observe(
                observed_at=monotonic(),
                captured_at_ms=int(captured_at_ms),
                generation=stream.generation,
                backend=stream.backend_name,
            )
    except BaseException as exc:
        monitor.fail(exc)
    finally:
        monitor.finish()


def _qualifying_recovery_frame(
    recovery: _RecoveryAttempt,
    latest: _FrameObservation | None,
) -> _FrameObservation | None:
    if latest is None:
        return None
    if latest.frame_number <= recovery.baseline_frame_count:
        return None
    if latest.generation <= recovery.baseline_generation:
        return None
    if latest.captured_at_ms < recovery.requested_at_ms:
        return None
    return latest


def _pass_recovery(
    recovery: _RecoveryAttempt,
    *,
    observation: _FrameObservation,
) -> None:
    recovery.passed = True
    recovery.observed_generation = observation.generation
    recovery.first_frame_number = observation.frame_number
    recovery.first_frame_captured_at_ms = observation.captured_at_ms
    recovery.latency_seconds = max(0.0, observation.observed_at - recovery.requested_at)
    recovery.backend = observation.backend


def _fail_recovery(
    recovery: _RecoveryAttempt,
    *,
    code: str,
    detail: str,
    generation: int,
    backend: str | None,
) -> None:
    recovery.passed = False
    recovery.failure_code = code
    recovery.failure_detail = detail
    recovery.observed_generation = generation
    recovery.backend = backend


def _gate_reasons(
    config: CameraSoakConfig,
    *,
    frame_count: int,
    observed_duration: float,
    recoveries: list[_RecoveryAttempt],
    lifecycle_snapshots: list[dict[str, object]],
    initial_backend: str | None,
    run_error: str | None,
    terminal_error: str | None,
    cleanup_errors: list[str],
    worker_alive_before_close: bool | None,
    worker_alive_after_close: bool | None,
) -> list[dict[str, object]]:
    reasons: list[dict[str, object]] = []
    if run_error is not None:
        reasons.append({"code": "run_error", "detail": run_error})
    if terminal_error is not None:
        reasons.append({"code": "terminal_error", "detail": terminal_error})
    for error in cleanup_errors:
        reasons.append({"code": "cleanup_error", "detail": error})
    if worker_alive_before_close is False:
        reasons.append({"code": "worker_not_alive_before_close"})
    if worker_alive_after_close:
        reasons.append({"code": "worker_alive_after_close"})
    if initial_backend is None:
        reasons.append({"code": "missing_camera_backend"})
    if not lifecycle_snapshots:
        reasons.append({"code": "missing_lifecycle_snapshots"})
    if len(recoveries) != config.forced_recovery_count:
        reasons.append(
            {
                "code": "forced_recoveries_not_requested",
                "actual": len(recoveries),
                "expected": config.forced_recovery_count,
            }
        )
    for recovery in recoveries:
        if recovery.passed is not True:
            reasons.append(
                {
                    "code": recovery.failure_code or "recovery_not_proven",
                    "sequence": recovery.sequence,
                    "detail": recovery.failure_detail,
                }
            )
    fps = frame_count / observed_duration if observed_duration > 0 else 0.0
    if fps < config.minimum_fps:
        reasons.append(
            {
                "code": "insufficient_fps",
                "actual": _rounded(fps),
                "minimum": config.minimum_fps,
            }
        )
    return reasons


def _build_report(
    config: CameraSoakConfig,
    *,
    invocation_started: float,
    exercise_started: float | None,
    observed_duration: float,
    frame_count: int,
    latest: _FrameObservation | None,
    initial_backend: str | None,
    final_backend: object,
    initial_generation: int | None,
    final_generation: object,
    lifecycle_snapshots: list[dict[str, object]],
    recoveries: list[_RecoveryAttempt],
    terminal_error: str | None,
    worker_alive_before_close: bool | None,
    worker_alive_after_close: bool | None,
    reasons: list[dict[str, object]],
) -> dict[str, object]:
    fps = frame_count / observed_duration if observed_duration > 0 else 0.0
    recovery_payload = []
    for recovery in recoveries:
        payload = asdict(recovery)
        payload["requested_at_seconds"] = _rounded(
            recovery.requested_at - invocation_started
        )
        payload["latency_seconds"] = _rounded_optional(recovery.latency_seconds)
        payload.pop("requested_at")
        payload.pop("requested_at_ms")
        payload.pop("deadline")
        payload.pop("baseline_frame_count")
        recovery_payload.append(payload)
    return {
        "metadata": {
            "schema": REPORT_SCHEMA,
            "schema_version": REPORT_SCHEMA_VERSION,
            "timestamp_policy": "monotonic_relative_seconds",
        },
        "test_scope": {
            "forced_recovery_mechanism": "CameraStream.request_recovery",
            "diagnostic_close_reopen_tested": bool(config.forced_recovery_count),
            "physical_unplug_replug_tested": False,
            "physical_unplug_replug_proven": False,
            "limitation": (
                "Forced recovery validates the internal close/reopen path; it does not "
                "prove physical camera unplug/replug behavior."
            ),
        },
        "configuration": {
            "camera_index": config.camera_index,
            "duration_seconds": config.duration_seconds,
            "forced_recovery_count": config.forced_recovery_count,
            "minimum_fps": config.minimum_fps,
            "max_recovery_seconds": config.max_recovery_seconds,
        },
        "camera": {
            "initial_backend": initial_backend,
            "final_backend": final_backend,
            "initial_generation": initial_generation,
            "final_generation": final_generation,
            "frames_consumed": frame_count,
            "observed_duration_seconds": _rounded(observed_duration),
            "fps": _rounded(fps),
            "last_frame_captured_at_ms": (
                latest.captured_at_ms if latest is not None else None
            ),
            "terminal_error": terminal_error,
            "worker_alive_before_close": worker_alive_before_close,
            "worker_alive_after_close": worker_alive_after_close,
        },
        "lifecycle_snapshots": lifecycle_snapshots,
        "recoveries": {
            "requested": len(recoveries),
            "proven": sum(recovery.passed is True for recovery in recoveries),
            "attempts": recovery_payload,
        },
        "result": {
            "passed": not reasons,
            "reasons": reasons,
        },
        "_timing": {
            "exercise_started_seconds": (
                _rounded(exercise_started - invocation_started)
                if exercise_started is not None
                else None
            )
        },
    }


def _safe_stream_value(stream: _CameraStreamLike | None, name: str) -> object:
    if stream is None:
        return None
    try:
        return getattr(stream, name)
    except BaseException:
        return None


def _describe_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def _validate_int(name: str, value: object, *, minimum: int, maximum: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")


def _validate_float(
    name: str,
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    numeric = float(value)
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")


def _camera_index(value: str) -> int:
    return _bounded_int(value, minimum=0, maximum=64, label="camera index")


def _duration(value: str) -> float:
    return _bounded_float(
        value,
        minimum=0.01,
        maximum=86_400.0,
        label="duration",
    )


def _forced_recoveries(value: str) -> int:
    return _bounded_int(
        value,
        minimum=0,
        maximum=1_000,
        label="forced recoveries",
    )


def _minimum_fps(value: str) -> float:
    return _bounded_float(
        value,
        minimum=0.01,
        maximum=1_000.0,
        label="minimum FPS",
    )


def _max_recovery_seconds(value: str) -> float:
    return _bounded_float(
        value,
        minimum=0.01,
        maximum=300.0,
        label="max recovery seconds",
    )


def _bounded_int(value: str, *, minimum: int, maximum: int, label: str) -> int:
    try:
        numeric = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be an integer") from exc
    if not minimum <= numeric <= maximum:
        raise argparse.ArgumentTypeError(
            f"{label} must be between {minimum} and {maximum}"
        )
    return numeric


def _bounded_float(
    value: str,
    *,
    minimum: float,
    maximum: float,
    label: str,
) -> float:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be a number") from exc
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        raise argparse.ArgumentTypeError(
            f"{label} must be between {minimum:g} and {maximum:g}"
        )
    return numeric


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _rounded_optional(value: float | None) -> float | None:
    return None if value is None else _rounded(value)


if __name__ == "__main__":  # pragma: no cover - exercised as a module
    raise SystemExit(main())


__all__ = [
    "CameraSoakConfig",
    "atomic_write_json",
    "build_parser",
    "main",
    "run_camera_soak",
]
