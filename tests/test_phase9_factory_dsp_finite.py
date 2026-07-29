from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from handmusic.music import builtin_synth
from handmusic.music.builtin_synth import BuiltinSynthOutput, SynthEngine
from handmusic.music.presets import PRESETS, Preset, get_preset


@pytest.mark.parametrize("resonance", (0.0, 0.25, 0.5, 0.75, 1.0))
def test_python_chamberlin_ceiling_matches_native_stability_contract(
    resonance: float,
) -> None:
    damping = builtin_synth._filter_damping(resonance)
    analytical_limit = builtin_synth._maximum_stable_filter_coefficient(damping)
    expected_ceiling = min(0.95, analytical_limit)
    coefficients = builtin_synth._state_variable_filter_coefficients(
        np.array([25.0, 1000.0, 20_000.0]),
        resonance,
        48_000.0,
    )

    assert np.all(coefficients <= expected_ceiling)
    assert expected_ceiling * expected_ceiling + 2.0 * damping * expected_ceiling < 4.0


@pytest.mark.parametrize(
    "preset",
    PRESETS,
    ids=lambda preset: f"{preset.program_id:03d}-{preset.name}",
)
def test_every_factory_preset_survives_sustained_finite_render(preset: Preset) -> None:
    synth = SynthEngine(sample_rate=48_000.0, program=preset.program_id)
    synth.control_change(74, 127)
    for note in (48, 60, 72):
        synth.note_on(note, 127)

    peak = 0.0
    for _ in range(30):
        block = synth.render(256)
        assert block.shape == (256, 2)
        assert block.dtype == np.float32
        assert np.isfinite(block).all()
        peak = max(peak, float(np.max(np.abs(block))))

    assert peak <= 1.0
    assert synth.nonfinite_recoveries == 0
    assert synth.last_render_error is None


@pytest.mark.parametrize("sample_rate", (32_000.0, 44_100.0, 48_000.0, 96_000.0))
@pytest.mark.parametrize("filter_type", ("lowpass", "highpass", "bandpass", "notch"))
def test_filter_extremes_remain_finite_without_recovery(
    sample_rate: float,
    filter_type: str,
) -> None:
    synth = SynthEngine(sample_rate=sample_rate, program=0)
    synth.apply_sound_patch(
        replace(
            get_preset(0),
            filter_type=filter_type,
            filter_cutoff_hz=20_000.0,
            filter_resonance=1.0,
            filter_envelope=1.0,
        ),
        brightness=1.0,
    )
    synth.note_on(96, 127)

    audio = np.concatenate([synth.render(256) for _ in range(40)])

    assert np.isfinite(audio).all()
    assert synth.nonfinite_recoveries == 0


def test_corrupt_filter_state_is_sanitized_and_observable() -> None:
    synth = SynthEngine(sample_rate=48_000.0, program=0)
    synth.note_on(60, 100)
    synth.voices[0].filter_low = float("nan")
    synth.voices[0].filter_band = float("inf")

    audio = synth.render(256)

    assert np.isfinite(audio).all()
    assert synth.nonfinite_recoveries == 1
    assert synth.last_render_error == "Invalid filter state reset before rendering"


class _FakeStream:
    def __init__(self, **kwargs: object) -> None:
        self.callback = kwargs["callback"]
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True


class _UnderflowStatus:
    output_underflow = True
    output_overflow = False

    def __bool__(self) -> bool:
        return True

    def __str__(self) -> str:
        return "output underflow"


def _fake_sounddevice() -> SimpleNamespace:
    return SimpleNamespace(
        query_devices=lambda **_kwargs: {"default_samplerate": 48_000.0},
        OutputStream=_FakeStream,
    )


def test_audio_callback_reports_portaudio_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sounddevice", _fake_sounddevice())
    output = BuiltinSynthOutput(program=0)
    block = np.empty((64, 2), dtype=np.float32)

    output._callback(block, 64, None, _UnderflowStatus())

    health = output.callback_health
    assert health.callback_count == 1
    assert health.status_event_count == 1
    assert health.output_underflows == 1
    assert health.output_overflows == 0
    assert health.render_failures == 0
    assert not health.healthy
    assert output.drain_callback_reports() == (
        "Audio callback status: output underflow",
    )
    assert output.drain_callback_reports() == ()
    output.close()


def test_audio_callback_reports_render_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sounddevice", _fake_sounddevice())
    output = BuiltinSynthOutput(program=0)
    block = np.full((64, 2), 1.0, dtype=np.float32)

    def fail_render(_frame_count: int) -> np.ndarray:
        raise FloatingPointError("synthetic DSP failure")

    monkeypatch.setattr(output._engine, "render", fail_render)
    output._callback(block, 64, None, None)

    assert np.count_nonzero(block) == 0
    health = output.callback_health
    assert health.callback_count == 1
    assert health.render_failures == 1
    assert health.last_error == "FloatingPointError: synthetic DSP failure"
    assert not health.healthy
    assert output.drain_callback_reports() == (
        "Audio render failed: FloatingPointError: synthetic DSP failure",
    )
    output.close()
