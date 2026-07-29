from __future__ import annotations

import ctypes
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from handmusic.music.native_audio_core import (
    AUDIO_CORE_ABI_VERSION,
    NativeAudioCoreOutput,
    SammyBlazeAudioPatchV1,
    bind_native_audio_core,
    find_native_audio_core_library,
    load_native_audio_core,
    patch_v1,
)
from handmusic.music.presets import get_preset
from handmusic.music.sound_parameters import FILTER_TYPE_ORDER, WAVEFORM_ORDER


class _FakeFunction:
    def __init__(self, implementation: Callable[..., Any]) -> None:
        self.implementation = implementation
        self.argtypes: list[object] | None = None
        self.restype: object | None = None

    def __call__(self, *args: object) -> object:
        return self.implementation(*args)


@dataclass
class _FakeNativeState:
    calls: list[tuple[object, ...]] = field(default_factory=list)
    active_voices: int = 0
    recoveries: int = 0
    render_value: float = 0.25
    render_error: BaseException | None = None
    patches: list[SammyBlazeAudioPatchV1] = field(default_factory=list)
    requested_unison_voices: int = 16
    rendered_unison_lanes_per_voice: int = 16
    unison_quality_limited: bool = False


def _fake_library(
    state: _FakeNativeState,
    *,
    prefix: str = "sbw_audio_core_",
    abi_version: int = AUDIO_CORE_ABI_VERSION,
    include_unison_diagnostics: bool = False,
) -> object:
    class Library:
        pass

    library = Library()

    def call(name: str, result: object = None) -> Callable[..., object]:
        def implementation(*args: object) -> object:
            state.calls.append((name, *args))
            return result

        return implementation

    setattr(library, f"{prefix}abi_version", _FakeFunction(lambda: abi_version))
    setattr(library, f"{prefix}create", _FakeFunction(call("create", 0x5B)))
    setattr(library, f"{prefix}destroy", _FakeFunction(call("destroy")))

    def note_on(_handle: object, note: int, velocity: float) -> int:
        state.calls.append(("note_on", note, velocity))
        state.active_voices += 1
        return 0

    def note_off(_handle: object, note: int) -> int:
        state.calls.append(("note_off", note))
        state.active_voices = max(0, state.active_voices - 1)
        return 0

    setattr(library, f"{prefix}note_on", _FakeFunction(note_on))
    setattr(library, f"{prefix}note_off", _FakeFunction(note_off))
    setattr(library, f"{prefix}control_change", _FakeFunction(call("cc", 0)))
    setattr(library, f"{prefix}program_change", _FakeFunction(call("program", 0)))

    def apply_patch(_handle: object, pointer: object) -> int:
        source = ctypes.cast(
            pointer,
            ctypes.POINTER(SammyBlazeAudioPatchV1),
        ).contents
        state.patches.append(
            SammyBlazeAudioPatchV1.from_buffer_copy(
                ctypes.string_at(ctypes.addressof(source), ctypes.sizeof(source))
            )
        )
        state.calls.append(("patch",))
        return 0

    setattr(library, f"{prefix}apply_patch", _FakeFunction(apply_patch))

    def render(_handle: object, output: object, frames: int) -> int:
        state.calls.append(("render", frames))
        if state.render_error is not None:
            raise state.render_error
        float_output = ctypes.cast(output, ctypes.POINTER(ctypes.c_float))
        for index in range(frames * 2):
            float_output[index] = state.render_value
        return 0

    setattr(library, f"{prefix}render_interleaved", _FakeFunction(render))

    def panic(_handle: object) -> int:
        state.calls.append(("panic",))
        state.active_voices = 0
        return 0

    setattr(library, f"{prefix}panic", _FakeFunction(panic))
    setattr(
        library,
        f"{prefix}active_voice_count",
        _FakeFunction(lambda _handle: state.active_voices),
    )
    setattr(
        library,
        f"{prefix}nonfinite_recovery_count",
        _FakeFunction(lambda _handle: state.recoveries),
    )
    if include_unison_diagnostics:
        setattr(
            library,
            f"{prefix}requested_unison_voices",
            _FakeFunction(lambda _handle: state.requested_unison_voices),
        )
        setattr(
            library,
            f"{prefix}rendered_unison_lanes_per_voice",
            _FakeFunction(lambda _handle: state.rendered_unison_lanes_per_voice),
        )
        setattr(
            library,
            f"{prefix}unison_quality_limited",
            _FakeFunction(lambda _handle: int(state.unison_quality_limited)),
        )
    return library


class _FakeStream:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class _FakeSoundDevice:
    def __init__(self) -> None:
        self.streams: list[_FakeStream] = []

    @staticmethod
    def query_devices(**_kwargs: object) -> dict[str, float]:
        return {"default_samplerate": 48_000.0}

    def OutputStream(self, **kwargs: object) -> _FakeStream:  # noqa: N802
        stream = _FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


class _UnderflowStatus:
    output_underflow = True
    output_overflow = False

    def __bool__(self) -> bool:
        return True

    def __str__(self) -> str:
        return "output underflow"


def _output(
    state: _FakeNativeState | None = None,
    **kwargs: object,
) -> tuple[NativeAudioCoreOutput, _FakeNativeState, _FakeSoundDevice]:
    state = state or _FakeNativeState()
    sounddevice = _FakeSoundDevice()
    output = NativeAudioCoreOutput(
        library=_fake_library(state),
        sounddevice_module=sounddevice,
        **kwargs,
    )
    return output, state, sounddevice


def test_phase9_2_patch_v1_has_exact_abi_layout_and_full_precision_values() -> None:
    expected_fields = [
        "struct_size",
        "abi_version",
        "program",
        "waveform_a",
        "waveform_b",
        "filter_type",
        "unison_voices",
        "waveform_mix",
        "attack_ms",
        "decay_ms",
        "sustain",
        "release_ms",
        "filter_cutoff_hz",
        "filter_resonance",
        "filter_envelope",
        "detune_cents",
        "vibrato_rate_hz",
        "vibrato_depth_semitones",
        "reverb_mix",
        "delay_mix",
        "delay_time_ms",
        "chorus_mix",
        "master_gain",
        "brightness",
    ]
    assert [name for name, _ctype in SammyBlazeAudioPatchV1._fields_] == expected_fields
    assert ctypes.sizeof(SammyBlazeAudioPatchV1) == 96

    preset = get_preset(37)
    patch = patch_v1(preset, master_gain=0.731234, brightness=0.418765)

    assert patch.struct_size == 96
    assert patch.abi_version == 1
    assert patch.program == preset.program_id
    assert patch.waveform_a == WAVEFORM_ORDER.index(preset.waveform_a)
    assert patch.waveform_b == WAVEFORM_ORDER.index(preset.waveform_b)
    assert patch.filter_type == FILTER_TYPE_ORDER.index(preset.filter_type)
    assert patch.unison_voices == preset.unison_voices
    assert patch.filter_cutoff_hz == pytest.approx(preset.filter_cutoff_hz)
    assert patch.master_gain == pytest.approx(0.731234)
    assert patch.brightness == pytest.approx(0.418765)
    assert patch.master_gain != pytest.approx(round(0.731234 * 127) / 127)


def test_phase9_2_binder_sets_exact_ctypes_prototypes_and_accepts_alias_prefix() -> None:
    state = _FakeNativeState()
    library = _fake_library(state, prefix="sammyblaze_audio_core_")

    api = bind_native_audio_core(library)

    assert api.export_names["create"] == "sammyblaze_audio_core_create"
    assert api.abi_version.argtypes == []
    assert api.abi_version.restype is ctypes.c_uint32
    assert api.create.argtypes == [ctypes.c_double, ctypes.c_uint32]
    assert api.create.restype is ctypes.c_void_p
    assert api.note_on.argtypes == [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_float,
    ]
    assert api.note_on.restype is ctypes.c_int32
    assert api.note_off.restype is ctypes.c_int32
    assert api.control_change.restype is ctypes.c_int32
    assert api.program_change.restype is ctypes.c_int32
    assert api.apply_patch.argtypes == [
        ctypes.c_void_p,
        ctypes.POINTER(SammyBlazeAudioPatchV1),
    ]
    assert api.render_interleaved.argtypes == [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_uint32,
    ]
    assert api.apply_patch.restype is ctypes.c_int32
    assert api.render_interleaved.restype is ctypes.c_int32
    assert api.panic.restype is ctypes.c_int32
    assert api.nonfinite_recovery_count.restype is ctypes.c_uint64
    assert api.requested_unison_voices is None
    assert api.rendered_unison_lanes_per_voice is None
    assert api.unison_quality_limited is None


def test_phase9_2_binder_rejects_mismatched_abi() -> None:
    with pytest.raises(RuntimeError, match="expected 1, found 2"):
        bind_native_audio_core(_fake_library(_FakeNativeState(), abi_version=2))


def test_phase9_2_library_search_prefers_explicit_then_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit = tmp_path / "explicit" / "SammyBlazeAudioCore.dll"
    environment = tmp_path / "environment" / "SammyBlazeAudioCore.dll"
    explicit.parent.mkdir()
    environment.parent.mkdir()
    explicit.touch()
    environment.touch()
    monkeypatch.setenv("SAMMYBLAZE_AUDIO_CORE_DLL", str(environment))

    assert find_native_audio_core_library(explicit) == explicit.resolve()
    assert find_native_audio_core_library() == environment.resolve()


def test_phase9_2_output_dispatches_note_sink_events_and_renders_interleaved() -> None:
    output, state, sounddevice = _output(program=4, block_size=64)
    preset = get_preset(37)
    output.note_on(60, 101)
    output.control_change(74, 96)
    output.note_off(60)
    output.program_change(12)
    output.apply_sound_patch(preset, master_gain=0.731234, brightness=0.418765)
    block = np.empty((64, 2), dtype=np.float32)

    output._callback(block, 64, None, None)

    assert sounddevice.streams[0].started
    assert sounddevice.streams[0].kwargs["channels"] == 2
    assert sounddevice.streams[0].kwargs["dtype"] == "float32"
    assert np.all(block == np.float32(0.25))
    call_names = [str(call[0]) for call in state.calls]
    assert call_names[:2] == ["create", "program"]
    assert call_names[2:7] == ["note_on", "cc", "note_off", "program", "patch"]
    assert call_names[7] == "render"
    note_on_call = next(call for call in state.calls if call[0] == "note_on")
    assert note_on_call[2] == pytest.approx(101 / 127.0)
    assert len(state.patches) == 1
    assert state.patches[0].master_gain == pytest.approx(0.731234)
    assert state.patches[0].brightness == pytest.approx(0.418765)
    assert output.callback_health.callback_count == 1
    assert output.callback_health.active_voice_count == 0

    output.close()
    output.close()
    assert sounddevice.streams[0].stopped
    assert sounddevice.streams[0].closed
    assert [call[0] for call in state.calls].count("destroy") == 1


def test_phase9_2_callback_reports_status_and_native_recoveries() -> None:
    state = _FakeNativeState(recoveries=3)
    output, _state, _sounddevice = _output(state, block_size=64)
    block = np.empty((64, 2), dtype=np.float32)

    output._callback(block, 64, None, _UnderflowStatus())

    health = output.callback_health
    assert health.callback_count == 1
    assert health.status_event_count == 1
    assert health.output_underflows == 1
    assert health.nonfinite_recoveries == 3
    assert not health.healthy
    assert output.drain_callback_reports() == (
        "Audio callback status: output underflow",
        "Native audio recovered from 3 new non-finite DSP event(s)",
    )
    output.close()


def test_phase9_3_optional_unison_diagnostics_are_observable_and_deduplicated() -> None:
    state = _FakeNativeState(
        requested_unison_voices=16,
        rendered_unison_lanes_per_voice=4,
        unison_quality_limited=True,
    )
    library = _fake_library(state, include_unison_diagnostics=True)
    sounddevice = _FakeSoundDevice()
    output = NativeAudioCoreOutput(
        library=library,
        sounddevice_module=sounddevice,
        block_size=64,
    )
    block = np.empty((64, 2), dtype=np.float32)

    output._callback(block, 64, None, None)
    output._callback(block, 64, None, None)

    health = output.callback_health
    assert health.requested_unison_voices == 16
    assert health.rendered_unison_lanes_per_voice == 4
    assert health.unison_quality_limited is True
    assert output.drain_callback_reports() == (
        "Native unison quality budget active: requested 16, rendering "
        "4 lanes/voice",
    )

    state.rendered_unison_lanes_per_voice = 16
    state.unison_quality_limited = False
    output._callback(block, 64, None, None)
    assert output.callback_health.unison_quality_limited is False
    assert output.drain_callback_reports() == (
        "Native unison full quality: 16 lanes/voice",
    )
    output.close()


def test_phase9_2_no_exception_escapes_callback_and_output_is_silenced() -> None:
    state = _FakeNativeState(render_error=KeyboardInterrupt("native failure"))
    output, _state, _sounddevice = _output(state, block_size=64)
    block = np.full((64, 2), 1.0, dtype=np.float32)

    output._callback(block, 64, None, None)

    assert np.count_nonzero(block) == 0
    health = output.callback_health
    assert health.render_failures == 1
    assert health.last_error == "KeyboardInterrupt: native failure"
    assert not health.healthy
    assert output.drain_callback_reports() == (
        "Native audio callback failed: KeyboardInterrupt: native failure",
    )
    assert ("panic",) in state.calls
    output.close()


def test_phase9_2_nonzero_native_status_is_reported_and_cannot_escape_callback() -> None:
    state = _FakeNativeState()
    library = _fake_library(state)
    library.sbw_audio_core_render_interleaved = _FakeFunction(
        lambda _handle, _output, _frames: -3
    )
    sounddevice = _FakeSoundDevice()
    output = NativeAudioCoreOutput(
        library=library,
        sounddevice_module=sounddevice,
        block_size=64,
    )
    block = np.full((64, 2), 1.0, dtype=np.float32)

    output._callback(block, 64, None, None)

    assert np.count_nonzero(block) == 0
    health = output.callback_health
    assert health.render_failures == 1
    assert health.last_error == (
        "RuntimeError: native render_interleaved failed: render failed (-3)"
    )
    assert output.drain_callback_reports() == (
        "Native audio callback failed: RuntimeError: native render_interleaved "
        "failed: render failed (-3)",
    )
    assert ("panic",) in state.calls
    output.close()


def test_phase9_2_event_queue_overflow_is_observable_and_safely_panics() -> None:
    output, state, _sounddevice = _output(
        block_size=64,
        event_queue_size=1,
        max_events_per_callback=1,
    )
    output.note_on(60, 100)
    output.note_off(60)
    block = np.empty((64, 2), dtype=np.float32)

    output._callback(block, 64, None, None)

    health = output.callback_health
    assert health.event_queue_overflows == 1
    assert not health.healthy
    assert ("panic",) in state.calls
    assert not any(call[0] == "note_on" for call in state.calls)
    assert output.drain_callback_reports() == (
        "Native audio event queue overflow; pending events were discarded "
        "and a safety panic was requested",
    )
    output.close()


def test_phase9_2_callback_rejects_oversized_or_noninterleaved_buffers_safely() -> None:
    output, state, _sounddevice = _output(block_size=64)
    oversized = np.ones((65, 2), dtype=np.float32)

    output._callback(oversized, 65, None, None)

    assert np.count_nonzero(oversized) == 0
    assert output.callback_health.render_failures == 1
    assert ("panic",) in state.calls
    output.close()


def test_phase9_2_optional_real_native_core_smoke() -> None:
    path = find_native_audio_core_library(required=False)
    if path is None:
        pytest.skip("SammyBlazeAudioCore native library is not available")

    _library, api, _loaded_path = load_native_audio_core(path)
    handle_value = api.create(48_000.0, 256)
    handle = (
        handle_value
        if isinstance(handle_value, ctypes.c_void_p)
        else ctypes.c_void_p(handle_value)
    )
    assert handle.value
    block = np.zeros((256, 2), dtype=np.float32)
    try:
        preset = patch_v1(get_preset(0))
        api.apply_patch(handle, ctypes.byref(preset))
        assert api.note_on(handle, 60, ctypes.c_float(100 / 127.0)) == 0
        assert (
            api.render_interleaved(
                handle,
                block.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                256,
            )
            == 0
        )
        assert np.isfinite(block).all()
        assert int(api.active_voice_count(handle)) >= 1
        assert int(api.nonfinite_recovery_count(handle)) == 0
        assert api.panic(handle) == 0
    finally:
        api.destroy(handle)
