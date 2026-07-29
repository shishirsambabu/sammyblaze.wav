"""Production native SoundDevice soak test with deterministic JSON reporting."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Final

from handmusic.music.native_audio_core import (
    AUDIO_CORE_ABI_VERSION,
    NativeAudioCallbackHealth,
    NativeAudioCallbackTiming,
    NativeAudioCoreOutput,
)
from handmusic.music.presets import Preset, get_preset

REPORT_SCHEMA: Final = "sammyblaze.native-audio-soak"
REPORT_SCHEMA_VERSION: Final = 1
DEFAULT_DURATION_SECONDS: Final = 60.0
DEFAULT_SAMPLE_RATE: Final = 48_000.0
DEFAULT_BLOCK_SIZE: Final = 256
DEFAULT_P95_DEADLINE_RATIO: Final = 0.50
DEFAULT_MAX_DEADLINE_MISSES: Final = 0
MINIMUM_CALLBACK_RATIO: Final = 0.80
CONTROL_BATCH_SIZE: Final = 6
SOAK_PROGRAM: Final = 80
SOAK_MASTER_GAIN: Final = 0.04
SOAK_NOTES: Final = tuple(36 + (index * 2) for index in range(24))


@dataclass(frozen=True, slots=True)
class AudioSoakConfig:
    """Validated configuration for one native audio soak."""

    duration_seconds: float = DEFAULT_DURATION_SECONDS
    block_size: int = DEFAULT_BLOCK_SIZE
    sample_rate: float = DEFAULT_SAMPLE_RATE
    device: int | str | None = None
    max_deadline_misses: int = DEFAULT_MAX_DEADLINE_MISSES
    p95_deadline_ratio_limit: float = DEFAULT_P95_DEADLINE_RATIO
    dll_path: str | os.PathLike[str] | None = None

    def __post_init__(self) -> None:
        _validate_finite_range(
            "duration_seconds",
            self.duration_seconds,
            minimum=0.001,
            maximum=3_600.0,
        )
        if (
            isinstance(self.block_size, bool)
            or not isinstance(self.block_size, int)
            or not 16 <= self.block_size <= 8_192
        ):
            raise ValueError("block_size must be an integer between 16 and 8192")
        _validate_finite_range(
            "sample_rate",
            self.sample_rate,
            minimum=8_000.0,
            maximum=384_000.0,
        )
        if isinstance(self.device, bool) or (
            self.device is not None
            and (
                not isinstance(self.device, (int, str))
                or (isinstance(self.device, int) and self.device < 0)
                or (isinstance(self.device, str) and not self.device.strip())
            )
        ):
            raise ValueError(
                "device must be a non-negative index, non-empty name, or None"
            )
        if (
            isinstance(self.max_deadline_misses, bool)
            or not isinstance(self.max_deadline_misses, int)
            or self.max_deadline_misses < 0
        ):
            raise ValueError("max_deadline_misses must be a non-negative integer")
        _validate_finite_range(
            "p95_deadline_ratio_limit",
            self.p95_deadline_ratio_limit,
            minimum=0.01,
            maximum=1.0,
        )

    @property
    def audio_deadline_seconds(self) -> float:
        return self.block_size / self.sample_rate

    @property
    def expected_callback_count(self) -> float:
        return self.duration_seconds / self.audio_deadline_seconds

    @property
    def minimum_callback_count(self) -> int:
        return max(1, math.floor(self.expected_callback_count * MINIMUM_CALLBACK_RATIO))

    @property
    def timing_ring_capacity(self) -> int:
        setup_and_cleanup_allowance = 1_024
        return math.ceil(self.expected_callback_count) + setup_and_cleanup_allowance


def run_audio_soak(
    config: AudioSoakConfig,
    *,
    output_factory: Callable[..., NativeAudioCoreOutput] = NativeAudioCoreOutput,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    output_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run a heavy native-audio soak and return a deterministic report object."""

    if not isinstance(config, AudioSoakConfig):
        raise TypeError("config must be an AudioSoakConfig")

    output: NativeAudioCoreOutput | None = None
    health: NativeAudioCallbackHealth | None = None
    timing: NativeAudioCallbackTiming | None = None
    callback_reports: tuple[str, ...] = ()
    run_error: str | None = None
    cleanup_errors: list[str] = []
    observed_duration = 0.0
    exercise_callback_count: int | None = None

    output_kwargs: dict[str, object] = {
        "program": SOAK_PROGRAM,
        "block_size": config.block_size,
        "sample_rate": config.sample_rate,
        "device": config.device,
        "timing_ring_capacity": config.timing_ring_capacity,
    }
    if config.dll_path is not None:
        output_kwargs["dll_path"] = config.dll_path
    if output_overrides:
        output_kwargs.update(output_overrides)

    try:
        output = output_factory(**output_kwargs)
        output.apply_sound_patch(
            _heavy_soak_patch(),
            master_gain=SOAK_MASTER_GAIN,
            brightness=0.72,
        )
        output.control_change(64, 127)
        _enqueue_notes_with_bounded_pacing(
            output,
            sleep=sleep,
            interval_seconds=config.audio_deadline_seconds,
        )

        callbacks_before_exercise = output.callback_health.callback_count
        started = monotonic()
        while True:
            elapsed = monotonic() - started
            if elapsed >= config.duration_seconds:
                observed_duration = elapsed
                break
            sleep(min(0.050, config.duration_seconds - elapsed))
        exercise_callback_count = (
            output.callback_health.callback_count - callbacks_before_exercise
        )
    except BaseException as exc:
        run_error = f"{type(exc).__name__}: {exc}"
    finally:
        if output is not None:
            try:
                output.control_change(64, 0)
            except BaseException as exc:
                cleanup_errors.append(f"sustain_off: {type(exc).__name__}: {exc}")
            try:
                output.panic()
            except BaseException as exc:
                cleanup_errors.append(f"panic: {type(exc).__name__}: {exc}")
            try:
                sleep(config.audio_deadline_seconds)
            except BaseException as exc:
                cleanup_errors.append(f"panic_pacing: {type(exc).__name__}: {exc}")
            try:
                output.close()
            except BaseException as exc:
                cleanup_errors.append(f"close: {type(exc).__name__}: {exc}")
            try:
                health = output.callback_health
                timing = output.callback_timing_snapshot()
                callback_reports = output.drain_callback_reports()
            except BaseException as exc:
                cleanup_errors.append(f"snapshot: {type(exc).__name__}: {exc}")

    reasons = _gate_reasons(
        config,
        health=health,
        timing=timing,
        run_error=run_error,
        cleanup_errors=cleanup_errors,
        exercise_callback_count=exercise_callback_count,
    )
    return _build_report(
        config,
        health=health,
        timing=timing,
        callback_reports=callback_reports,
        observed_duration=observed_duration,
        exercise_callback_count=exercise_callback_count,
        reasons=reasons,
    )


def atomic_write_json(path: str | os.PathLike[str], report: dict[str, object]) -> None:
    """Write a report atomically in its destination directory."""

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
        description="Soak the SammyBlaze native SoundDevice audio path.",
    )
    parser.add_argument(
        "--duration",
        type=_positive_float,
        default=DEFAULT_DURATION_SECONDS,
        help="soak duration in seconds (0.001-3600)",
    )
    parser.add_argument(
        "--block-size",
        type=_block_size,
        default=DEFAULT_BLOCK_SIZE,
        help="audio callback block size in frames (16-8192)",
    )
    parser.add_argument(
        "--sample-rate",
        type=_sample_rate,
        default=DEFAULT_SAMPLE_RATE,
        help="sample rate in Hz (8000-384000)",
    )
    parser.add_argument(
        "--device",
        type=_device,
        default=None,
        help="optional SoundDevice output index or exact device name",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("sammyblaze-audio-soak.json"),
        help="destination for the atomic machine-readable report",
    )
    parser.add_argument(
        "--max-deadline-misses",
        type=_non_negative_int,
        default=DEFAULT_MAX_DEADLINE_MISSES,
        help="maximum accepted callback deadline misses",
    )
    parser.add_argument(
        "--p95-deadline-ratio",
        type=_deadline_ratio,
        default=DEFAULT_P95_DEADLINE_RATIO,
        help="maximum accepted p95 callback time as a fraction of the deadline",
    )
    parser.add_argument(
        "--dll-path",
        type=Path,
        default=None,
        help="optional path to SammyBlazeAudioCore",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        config = AudioSoakConfig(
            duration_seconds=arguments.duration,
            block_size=arguments.block_size,
            sample_rate=arguments.sample_rate,
            device=arguments.device,
            max_deadline_misses=arguments.max_deadline_misses,
            p95_deadline_ratio_limit=arguments.p95_deadline_ratio,
            dll_path=arguments.dll_path,
        )
        report = run_audio_soak(config)
        atomic_write_json(arguments.output_json, report)
    except (TypeError, ValueError) as exc:
        parser.error(str(exc))

    print(json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True))
    result = report["result"]
    assert isinstance(result, dict)
    return 0 if result["passed"] else 1


def _heavy_soak_patch() -> Preset:
    return replace(
        get_preset(SOAK_PROGRAM),
        unison_voices=16,
        sustain=0.88,
        reverb_mix=0.38,
        delay_mix=0.28,
        delay_time_ms=375.0,
        chorus_mix=0.24,
    )


def _enqueue_notes_with_bounded_pacing(
    output: NativeAudioCoreOutput,
    *,
    sleep: Callable[[float], None],
    interval_seconds: float,
) -> None:
    for index, note in enumerate(SOAK_NOTES, start=1):
        output.note_on(note, 76)
        if index % CONTROL_BATCH_SIZE == 0:
            sleep(interval_seconds)


def _gate_reasons(
    config: AudioSoakConfig,
    *,
    health: NativeAudioCallbackHealth | None,
    timing: NativeAudioCallbackTiming | None,
    run_error: str | None,
    cleanup_errors: list[str],
    exercise_callback_count: int | None,
) -> list[dict[str, object]]:
    reasons: list[dict[str, object]] = []
    if run_error is not None:
        reasons.append({"code": "run_error", "detail": run_error})
    for error in cleanup_errors:
        reasons.append({"code": "cleanup_error", "detail": error})
    if health is None:
        reasons.append({"code": "missing_callback_health"})
    else:
        _append_nonzero(reasons, "output_underflows", health.output_underflows)
        _append_nonzero(reasons, "output_overflows", health.output_overflows)
        _append_nonzero(reasons, "callback_status_events", health.status_event_count)
        _append_nonzero(reasons, "render_failures", health.render_failures)
        _append_nonzero(reasons, "nonfinite_recoveries", health.nonfinite_recoveries)
        _append_nonzero(reasons, "event_queue_overflows", health.event_queue_overflows)
        _append_nonzero(
            reasons,
            "dropped_callback_reports",
            health.dropped_callback_reports,
        )
        if (
            exercise_callback_count is not None
            and exercise_callback_count < config.minimum_callback_count
        ):
            reasons.append(
                {
                    "code": "insufficient_callbacks",
                    "actual": exercise_callback_count,
                    "minimum": config.minimum_callback_count,
                }
            )
        if (
            health.requested_unison_voices is not None
            and health.requested_unison_voices != 16
        ):
            reasons.append(
                {
                    "code": "unexpected_requested_unison",
                    "actual": health.requested_unison_voices,
                    "expected": 16,
                }
            )
    if timing is None:
        reasons.append({"code": "missing_callback_timing"})
    else:
        if timing.sample_count == 0 or timing.p95_ms is None:
            reasons.append({"code": "missing_callback_timing_samples"})
        if timing.overwritten_sample_count:
            reasons.append(
                {
                    "code": "callback_timing_overwritten",
                    "actual": timing.overwritten_sample_count,
                    "limit": 0,
                }
            )
        if timing.deadline_miss_count > config.max_deadline_misses:
            reasons.append(
                {
                    "code": "deadline_misses",
                    "actual": timing.deadline_miss_count,
                    "limit": config.max_deadline_misses,
                }
            )
        ratio = timing.p95_deadline_ratio
        if ratio is not None and ratio > config.p95_deadline_ratio_limit:
            reasons.append(
                {
                    "code": "p95_deadline_ratio",
                    "actual": _rounded(ratio),
                    "limit": config.p95_deadline_ratio_limit,
                }
            )
        if health is not None and timing.sample_count != health.callback_count:
            reasons.append(
                {
                    "code": "callback_timing_count_mismatch",
                    "timing": timing.sample_count,
                    "health": health.callback_count,
                }
            )
    return reasons


def _build_report(
    config: AudioSoakConfig,
    *,
    health: NativeAudioCallbackHealth | None,
    timing: NativeAudioCallbackTiming | None,
    callback_reports: tuple[str, ...],
    observed_duration: float,
    exercise_callback_count: int | None,
    reasons: list[dict[str, object]],
) -> dict[str, object]:
    health_payload = asdict(health) if health is not None else None
    timing_payload: dict[str, object] | None = None
    if timing is not None:
        timing_payload = {
            **asdict(timing),
            "p50_ms": _rounded_optional(timing.p50_ms),
            "p95_ms": _rounded_optional(timing.p95_ms),
            "p99_ms": _rounded_optional(timing.p99_ms),
            "max_ms": _rounded_optional(timing.max_ms),
            "audio_deadline_ms": _rounded(timing.audio_deadline_ms),
            "p95_deadline_ratio": _rounded_optional(timing.p95_deadline_ratio),
        }
    return {
        "metadata": {
            "schema": REPORT_SCHEMA,
            "schema_version": REPORT_SCHEMA_VERSION,
            "timestamp_policy": "omitted_for_determinism",
        },
        "configuration": {
            "device": config.device,
            "sample_rate_hz": config.sample_rate,
            "block_size_frames": config.block_size,
            "duration_seconds": config.duration_seconds,
            "observed_exercise_seconds": _rounded(observed_duration),
            "expected_callback_count": _rounded(config.expected_callback_count),
            "minimum_callback_count": config.minimum_callback_count,
            "observed_exercise_callback_count": exercise_callback_count,
            "requested_unison_voices": 16,
            "simultaneous_note_count": len(SOAK_NOTES),
            "notes": list(SOAK_NOTES),
            "sustain_enabled": True,
            "effects_enabled": ["chorus", "delay", "reverb"],
            "master_gain": SOAK_MASTER_GAIN,
            "max_deadline_misses": config.max_deadline_misses,
            "p95_deadline_ratio_limit": config.p95_deadline_ratio_limit,
        },
        "native_audio": {
            "abi_version": (
                health.abi_version if health is not None else AUDIO_CORE_ABI_VERSION
            ),
            "library_path": health.library_path if health is not None else None,
            "callback_health": health_payload,
            "callback_reports": list(callback_reports),
        },
        "timing": timing_payload,
        "result": {
            "passed": not reasons,
            "reasons": reasons,
        },
    }


def _append_nonzero(
    reasons: list[dict[str, object]],
    code: str,
    value: int,
) -> None:
    if value:
        reasons.append({"code": code, "actual": value, "limit": 0})


def _validate_finite_range(
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


def _positive_float(value: str) -> float:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(numeric) or not 0.001 <= numeric <= 3_600.0:
        raise argparse.ArgumentTypeError("must be between 0.001 and 3600")
    return numeric


def _block_size(value: str) -> int:
    return _bounded_int(value, minimum=16, maximum=8_192, label="block size")


def _sample_rate(value: str) -> float:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sample rate must be a number") from exc
    if not math.isfinite(numeric) or not 8_000.0 <= numeric <= 384_000.0:
        raise argparse.ArgumentTypeError("sample rate must be between 8000 and 384000")
    return numeric


def _device(value: str) -> int | str:
    stripped = value.strip()
    if not stripped:
        raise argparse.ArgumentTypeError("device must not be empty")
    try:
        index = int(stripped)
    except ValueError:
        return stripped
    if index < 0:
        raise argparse.ArgumentTypeError("device index must not be negative")
    return index


def _non_negative_int(value: str) -> int:
    return _bounded_int(
        value,
        minimum=0,
        maximum=1_000_000,
        label="max deadline misses",
    )


def _deadline_ratio(value: str) -> float:
    try:
        numeric = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("deadline ratio must be a number") from exc
    if not math.isfinite(numeric) or not 0.01 <= numeric <= 1.0:
        raise argparse.ArgumentTypeError("deadline ratio must be between 0.01 and 1")
    return numeric


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


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _rounded_optional(value: float | None) -> float | None:
    return None if value is None else _rounded(value)


if __name__ == "__main__":  # pragma: no cover - exercised as a module
    raise SystemExit(main())


__all__ = [
    "AudioSoakConfig",
    "atomic_write_json",
    "build_parser",
    "main",
    "run_audio_soak",
]
