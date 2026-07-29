from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from handmusic.music.native_audio_core import (
    NativeAudioCallbackHealth,
    NativeAudioCallbackTiming,
)
from handmusic.reliability import audio_soak
from handmusic.reliability.audio_soak import (
    AudioSoakConfig,
    atomic_write_json,
    main,
    run_audio_soak,
)


class _FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.output: _FakeSoakOutput | None = None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration
        if self.output is not None:
            self.output.advance(duration)


class _FakeSoakOutput:
    def __init__(
        self,
        *,
        fake_time: _FakeTime,
        callback_duration_ms: float = 1.0,
        deadline_misses: int | None = None,
        callback_rate_multiplier: float = 1.0,
        health_overrides: dict[str, object] | None = None,
        fail_note_on: bool = False,
        **kwargs: object,
    ) -> None:
        self.kwargs = kwargs
        self.fake_time = fake_time
        self.fake_time.output = self
        self.callback_duration_ms = callback_duration_ms
        self.deadline_misses = deadline_misses
        self.callback_rate_multiplier = callback_rate_multiplier
        self.health_overrides = health_overrides or {}
        self.fail_note_on = fail_note_on
        self.callback_count = 0
        self.callback_fraction = 0.0
        self.events: list[tuple[object, ...]] = []
        self.patch: object | None = None
        self.panic_called = False
        self.closed = False
        self.block_size = int(kwargs["block_size"])
        self.sample_rate = float(kwargs["sample_rate"])
        self.ring_capacity = int(kwargs["timing_ring_capacity"])

    def advance(self, duration: float) -> None:
        callbacks = (
            duration
            * self.sample_rate
            / self.block_size
            * self.callback_rate_multiplier
        ) + self.callback_fraction
        whole_callbacks = int(callbacks)
        self.callback_fraction = callbacks - whole_callbacks
        self.callback_count += whole_callbacks

    def apply_sound_patch(
        self,
        preset: object,
        *,
        master_gain: float,
        brightness: float,
    ) -> None:
        self.patch = preset
        self.events.append(("patch", master_gain, brightness))

    def control_change(self, control: int, value: int) -> None:
        self.events.append(("cc", control, value))

    def note_on(self, note: int, velocity: int) -> None:
        self.events.append(("note_on", note, velocity))
        if self.fail_note_on:
            raise RuntimeError("injected note failure")

    def panic(self) -> None:
        self.panic_called = True
        self.events.append(("panic",))

    def close(self) -> None:
        self.closed = True

    @property
    def callback_health(self) -> NativeAudioCallbackHealth:
        values: dict[str, object] = {
            "callback_count": self.callback_count,
            "status_event_count": 0,
            "output_underflows": 0,
            "output_overflows": 0,
            "render_failures": 0,
            "nonfinite_recoveries": 0,
            "last_status": None,
            "last_error": None,
            "event_queue_overflows": 0,
            "dropped_callback_reports": 0,
            "active_voice_count": 0,
            "requested_unison_voices": None,
            "rendered_unison_lanes_per_voice": None,
            "unison_quality_limited": None,
            "abi_version": 1,
            "library_path": "C:/fake/SammyBlazeAudioCore.dll",
            "requested_output_device": self.kwargs.get("device"),
            "output_device_index": 7,
            "output_device_name": "Fake Output",
            "output_host_api": "Fake API",
            "sample_rate": self.sample_rate,
            "block_size": self.block_size,
        }
        values.update(self.health_overrides)
        return NativeAudioCallbackHealth(**values)

    def callback_timing_snapshot(self) -> NativeAudioCallbackTiming:
        deadline_ms = self.block_size / self.sample_rate * 1_000.0
        deadline_misses = (
            self.deadline_misses
            if self.deadline_misses is not None
            else int(self.callback_duration_ms > deadline_ms) * self.callback_count
        )
        return NativeAudioCallbackTiming(
            sample_count=self.callback_count,
            retained_sample_count=self.callback_count,
            overwritten_sample_count=0,
            ring_capacity=self.ring_capacity,
            audio_deadline_ms=deadline_ms,
            deadline_miss_count=deadline_misses,
            p50_ms=self.callback_duration_ms,
            p95_ms=self.callback_duration_ms,
            p99_ms=self.callback_duration_ms,
            max_ms=self.callback_duration_ms,
        )

    @staticmethod
    def drain_callback_reports() -> tuple[str, ...]:
        return ()


def _run_fake_soak(
    config: AudioSoakConfig | None = None,
    **output_options: object,
) -> tuple[dict[str, object], _FakeSoakOutput]:
    fake_time = _FakeTime()
    created: list[_FakeSoakOutput] = []

    def factory(**kwargs: object) -> _FakeSoakOutput:
        output = _FakeSoakOutput(
            fake_time=fake_time,
            **output_options,
            **kwargs,
        )
        created.append(output)
        return output

    report = run_audio_soak(
        config
        or AudioSoakConfig(
            duration_seconds=0.1,
            block_size=64,
            sample_rate=8_000.0,
            device=7,
        ),
        output_factory=factory,
        sleep=fake_time.sleep,
        monotonic=fake_time.monotonic,
    )
    return report, created[0]


def test_phase9_4_soak_passes_heavy_patch_and_legacy_optional_diagnostics() -> None:
    report, output = _run_fake_soak()

    assert report["result"] == {"passed": True, "reasons": []}
    assert output.kwargs["device"] == 7
    assert output.kwargs["sample_rate"] == 8_000.0
    assert output.kwargs["block_size"] == 64
    assert output.panic_called
    assert output.closed
    assert output.events[0] == ("patch", 0.04, 0.72)
    assert output.events[1] == ("cc", 64, 127)
    assert output.events[-2:] == [("cc", 64, 0), ("panic",)]
    note_events = [event for event in output.events if event[0] == "note_on"]
    assert len(note_events) == 24
    assert output.patch is not None
    assert output.patch.unison_voices == 16
    assert output.patch.sustain == pytest.approx(0.88)
    assert output.patch.reverb_mix > 0
    assert output.patch.delay_mix > 0
    health = report["native_audio"]["callback_health"]
    assert health["requested_unison_voices"] is None
    assert health["output_device_index"] == 7
    assert health["output_host_api"] == "Fake API"
    assert report["metadata"]["timestamp_policy"] == "omitted_for_determinism"


def test_phase9_4_soak_reports_all_reliability_gate_failures() -> None:
    config = AudioSoakConfig(
        duration_seconds=0.1,
        block_size=64,
        sample_rate=8_000.0,
        max_deadline_misses=0,
    )
    report, output = _run_fake_soak(
        config,
        callback_duration_ms=6.0,
        health_overrides={
            "status_event_count": 1,
            "output_underflows": 1,
            "render_failures": 2,
            "nonfinite_recoveries": 3,
            "event_queue_overflows": 4,
        },
    )

    assert report["result"]["passed"] is False
    codes = {reason["code"] for reason in report["result"]["reasons"]}
    assert {
        "output_underflows",
        "callback_status_events",
        "render_failures",
        "nonfinite_recoveries",
        "event_queue_overflows",
        "p95_deadline_ratio",
    } <= codes
    assert output.panic_called
    assert output.closed


def test_phase9_4_soak_rejects_inadequate_callback_delivery() -> None:
    report, _output = _run_fake_soak(callback_rate_multiplier=0.0)

    assert report["result"]["passed"] is False
    codes = {reason["code"] for reason in report["result"]["reasons"]}
    assert "insufficient_callbacks" in codes
    assert "missing_callback_timing_samples" in codes
    assert report["configuration"]["observed_exercise_callback_count"] == 0


def test_phase9_4_configurable_deadline_miss_limit() -> None:
    base = AudioSoakConfig(
        duration_seconds=0.01,
        block_size=64,
        sample_rate=8_000.0,
        max_deadline_misses=10,
    )
    report, _output = _run_fake_soak(base, deadline_misses=2)

    assert report["result"]["passed"] is True
    assert report["timing"]["deadline_miss_count"] == 2

    failed, _output = _run_fake_soak(
        replace(base, max_deadline_misses=1),
        deadline_misses=2,
    )
    assert failed["result"]["passed"] is False
    assert "deadline_misses" in {
        reason["code"] for reason in failed["result"]["reasons"]
    }


def test_phase9_4_soak_always_panics_and_closes_after_body_failure() -> None:
    report, output = _run_fake_soak(fail_note_on=True)

    assert report["result"]["passed"] is False
    assert report["result"]["reasons"][0]["code"] == "run_error"
    assert "injected note failure" in report["result"]["reasons"][0]["detail"]
    assert output.panic_called
    assert output.closed


def test_phase9_4_atomic_report_is_sorted_valid_and_leaves_no_temp(
    tmp_path: Path,
) -> None:
    report, _output = _run_fake_soak()
    destination = tmp_path / "nested" / "soak.json"

    atomic_write_json(destination, report)
    first = destination.read_bytes()
    atomic_write_json(destination, report)

    assert destination.read_bytes() == first
    assert json.loads(first) == report
    assert not list(destination.parent.glob("*.tmp"))
    assert b'"configuration"' < b'"metadata"'


def test_phase9_4_cli_writes_machine_report_and_returns_gate_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report, _output = _run_fake_soak()
    destination = tmp_path / "cli-report.json"
    monkeypatch.setattr(audio_soak, "run_audio_soak", lambda _config: report)

    exit_code = audio_soak.main(
        [
            "--duration",
            "0.1",
            "--block-size",
            "64",
            "--sample-rate",
            "8000",
            "--device",
            "Studio Output",
            "--output-json",
            str(destination),
        ]
    )

    assert exit_code == 0
    assert json.loads(destination.read_text(encoding="utf-8")) == report
    assert json.loads(capsys.readouterr().out) == report


@pytest.mark.parametrize(
    "arguments",
    [
        ["--duration", "0"],
        ["--duration", "nan"],
        ["--block-size", "15"],
        ["--sample-rate", "7999"],
        ["--device", "-1"],
        ["--max-deadline-misses", "-1"],
        ["--p95-deadline-ratio", "1.1"],
    ],
)
def test_phase9_4_cli_rejects_invalid_arguments(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"duration_seconds": 0},
        {"block_size": True},
        {"sample_rate": float("inf")},
        {"device": ""},
        {"max_deadline_misses": True},
        {"p95_deadline_ratio_limit": 0},
    ],
)
def test_phase9_4_config_rejects_invalid_values(changes: dict[str, object]) -> None:
    base = AudioSoakConfig()

    with pytest.raises(ValueError):
        replace(base, **changes)
