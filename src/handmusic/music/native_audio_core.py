"""ctypes/SoundDevice adapter for the versioned SammyBlaze native audio core.

The module deliberately contains no fallback synthesizer.  It either loads ABI v1
of the native core and owns it for the lifetime of the output stream, or fails with
an actionable error that includes the searched locations.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event
from typing import Any, Final

import numpy as np

from handmusic.music.presets import Preset, get_preset
from handmusic.music.sound_parameters import FILTER_TYPE_ORDER, WAVEFORM_ORDER

AUDIO_CORE_ABI_VERSION: Final = 1
DEFAULT_BLOCK_SIZE: Final = 256
DEFAULT_EVENT_QUEUE_SIZE: Final = 512
DEFAULT_REPORT_QUEUE_SIZE: Final = 64
DEFAULT_MAX_EVENTS_PER_CALLBACK: Final = 128
DEFAULT_TIMING_RING_CAPACITY: Final = 65_536
STEREO_CHANNELS: Final = 2
_STATUS_NAMES: Final = {
    -3: "render failed",
    -2: "not ready",
    -1: "invalid argument",
}

_CANONICAL_LIBRARY_NAMES: Final = (
    "SammyBlazeAudioCore.dll",
    "sammyblaze_audio_core.dll",
    "libSammyBlazeAudioCore.so",
    "libsammyblaze_audio_core.so",
    "libSammyBlazeAudioCore.dylib",
    "libsammyblaze_audio_core.dylib",
)
_SYMBOL_PREFIXES: Final = (
    "sbw_audio_core_",
    "sammyblaze_audio_core_",
    "sammyblaze_core_",
    "audio_core_",
)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class SammyBlazeAudioPatchV1(ctypes.Structure):
    """Exact ABI v1 patch payload; floats retain native parameter precision."""

    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("program", ctypes.c_uint32),
        ("waveform_a", ctypes.c_uint32),
        ("waveform_b", ctypes.c_uint32),
        ("filter_type", ctypes.c_uint32),
        ("unison_voices", ctypes.c_uint32),
        ("waveform_mix", ctypes.c_float),
        ("attack_ms", ctypes.c_float),
        ("decay_ms", ctypes.c_float),
        ("sustain", ctypes.c_float),
        ("release_ms", ctypes.c_float),
        ("filter_cutoff_hz", ctypes.c_float),
        ("filter_resonance", ctypes.c_float),
        ("filter_envelope", ctypes.c_float),
        ("detune_cents", ctypes.c_float),
        ("vibrato_rate_hz", ctypes.c_float),
        ("vibrato_depth_semitones", ctypes.c_float),
        ("reverb_mix", ctypes.c_float),
        ("delay_mix", ctypes.c_float),
        ("delay_time_ms", ctypes.c_float),
        ("chorus_mix", ctypes.c_float),
        ("master_gain", ctypes.c_float),
        ("brightness", ctypes.c_float),
    ]


@dataclass(frozen=True, slots=True)
class NativeAudioCallbackHealth:
    """Lock-free diagnostic snapshot compatible with the Python synth's health."""

    callback_count: int
    status_event_count: int
    output_underflows: int
    output_overflows: int
    render_failures: int
    nonfinite_recoveries: int
    last_status: str | None
    last_error: str | None
    event_queue_overflows: int
    dropped_callback_reports: int
    active_voice_count: int
    requested_unison_voices: int | None
    rendered_unison_lanes_per_voice: int | None
    unison_quality_limited: bool | None
    abi_version: int
    library_path: str
    requested_output_device: int | str | None
    output_device_index: int | None
    output_device_name: str | None
    output_host_api: str | None
    sample_rate: float
    block_size: int

    @property
    def healthy(self) -> bool:
        return not (
            self.status_event_count
            or self.render_failures
            or self.nonfinite_recoveries
            or self.event_queue_overflows
        )


@dataclass(frozen=True, slots=True)
class NativeAudioCallbackTiming:
    """Post-stop callback-duration snapshot from the preallocated timing ring."""

    sample_count: int
    retained_sample_count: int
    overwritten_sample_count: int
    ring_capacity: int
    audio_deadline_ms: float
    deadline_miss_count: int
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_ms: float | None

    @property
    def p95_deadline_ratio(self) -> float | None:
        if self.p95_ms is None:
            return None
        return self.p95_ms / self.audio_deadline_ms


@dataclass(frozen=True, slots=True)
class NativeAudioCoreBindings:
    """Bound ABI functions and the concrete export names selected by the loader."""

    abi_version: Any
    create: Any
    destroy: Any
    note_on: Any
    note_off: Any
    control_change: Any
    program_change: Any
    apply_patch: Any
    render_interleaved: Any
    panic: Any
    active_voice_count: Any
    nonfinite_recovery_count: Any
    requested_unison_voices: Any | None
    rendered_unison_lanes_per_voice: Any | None
    unison_quality_limited: Any | None
    export_names: dict[str, str]


def _library_names() -> tuple[str, ...]:
    if sys.platform == "win32":
        return _CANONICAL_LIBRARY_NAMES[:2]
    if sys.platform == "darwin":
        return _CANONICAL_LIBRARY_NAMES[4:]
    return _CANONICAL_LIBRARY_NAMES[2:4]


def _expand_library_location(location: Path) -> tuple[Path, ...]:
    if location.suffix:
        return (location,)
    return tuple(location / name for name in _library_names())


def _packaged_roots() -> tuple[Path, ...]:
    module_path = Path(__file__).resolve()
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    roots.extend(
        (
            Path(sys.executable).resolve().parent,
            module_path.parent,
            module_path.parent.parent,
            module_path.parents[2],
        )
    )
    return tuple(roots)


def _candidate_library_paths(explicit_path: str | os.PathLike[str] | None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if explicit_path is not None:
        candidates.extend(_expand_library_location(Path(explicit_path).expanduser()))

    environment_path = os.environ.get("SAMMYBLAZE_AUDIO_CORE_DLL")
    if environment_path:
        candidates.extend(_expand_library_location(Path(environment_path).expanduser()))

    relative_directories = (
        Path(),
        Path("native"),
        Path("audio"),
        Path("lib"),
        Path("bin"),
        Path("Release"),
        Path("bin") / "Release",
        Path("native") / "Release",
        Path("native") / "audio_core",
        Path("native") / "audio_core" / "Release",
    )
    for root in _packaged_roots():
        for relative in relative_directories:
            candidates.extend(_expand_library_location(root / relative))

    build_root = Path("D:/SammyBlazeBuild/native")
    build_directories = (
        Path(),
        Path("Release"),
        Path("bin"),
        Path("bin") / "Release",
        Path("lib"),
        Path("lib") / "Release",
        Path("native") / "audio_core",
        Path("native") / "audio_core" / "Release",
        Path("native") / "audio_core" / "bin" / "Release",
        Path("audio_core"),
        Path("audio_core") / "Release",
    )
    for relative in build_directories:
        candidates.extend(_expand_library_location(build_root / relative))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized not in seen:
            seen.add(normalized)
            unique.append(candidate)
    return tuple(unique)


def find_native_audio_core_library(
    explicit_path: str | os.PathLike[str] | None = None,
    *,
    required: bool = True,
) -> Path | None:
    """Resolve the native core using the documented deterministic search order."""

    candidates = _candidate_library_paths(explicit_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    if not required:
        return None
    searched = "\n".join(f"  - {candidate}" for candidate in candidates)
    raise RuntimeError(
        "SammyBlazeAudioCore library was not found. Build/install the native audio "
        "core, pass dll_path, or set SAMMYBLAZE_AUDIO_CORE_DLL. Searched:\n"
        f"{searched}"
    )


def _resolve_symbol(library: object, suffix: str) -> tuple[Any, str]:
    attempted: list[str] = []
    for prefix in _SYMBOL_PREFIXES:
        name = f"{prefix}{suffix}"
        attempted.append(name)
        try:
            return getattr(library, name), name
        except AttributeError:
            continue
    raise RuntimeError(
        f"Native audio core is missing export for {suffix!r}; tried "
        + ", ".join(attempted)
    )


def _resolve_optional_symbol(library: object, suffix: str) -> tuple[Any | None, str | None]:
    for prefix in _SYMBOL_PREFIXES:
        name = f"{prefix}{suffix}"
        try:
            return getattr(library, name), name
        except AttributeError:
            continue
    return None, None


def bind_native_audio_core(library: object) -> NativeAudioCoreBindings:
    """Bind all ABI v1 functions with explicit ctypes signatures."""

    functions: dict[str, Any] = {}
    names: dict[str, str] = {}
    for logical_name in (
        "abi_version",
        "create",
        "destroy",
        "note_on",
        "note_off",
        "control_change",
        "program_change",
        "apply_patch",
        "render_interleaved",
        "panic",
        "active_voice_count",
        "nonfinite_recovery_count",
    ):
        functions[logical_name], names[logical_name] = _resolve_symbol(
            library, logical_name
        )

    handle = ctypes.c_void_p
    uint32 = ctypes.c_uint32
    functions["abi_version"].argtypes = []
    functions["abi_version"].restype = uint32
    functions["create"].argtypes = [ctypes.c_double, uint32]
    functions["create"].restype = handle
    functions["destroy"].argtypes = [handle]
    functions["destroy"].restype = None
    functions["note_on"].argtypes = [handle, uint32, ctypes.c_float]
    functions["note_on"].restype = ctypes.c_int32
    functions["note_off"].argtypes = [handle, uint32]
    functions["note_off"].restype = ctypes.c_int32
    functions["control_change"].argtypes = [handle, uint32, uint32]
    functions["control_change"].restype = ctypes.c_int32
    functions["program_change"].argtypes = [handle, uint32]
    functions["program_change"].restype = ctypes.c_int32
    functions["apply_patch"].argtypes = [
        handle,
        ctypes.POINTER(SammyBlazeAudioPatchV1),
    ]
    functions["apply_patch"].restype = ctypes.c_int32
    functions["render_interleaved"].argtypes = [
        handle,
        ctypes.POINTER(ctypes.c_float),
        uint32,
    ]
    functions["render_interleaved"].restype = ctypes.c_int32
    functions["panic"].argtypes = [handle]
    functions["panic"].restype = ctypes.c_int32
    functions["active_voice_count"].argtypes = [handle]
    functions["active_voice_count"].restype = uint32
    functions["nonfinite_recovery_count"].argtypes = [handle]
    functions["nonfinite_recovery_count"].restype = ctypes.c_uint64

    for logical_name in (
        "requested_unison_voices",
        "rendered_unison_lanes_per_voice",
        "unison_quality_limited",
    ):
        function, export_name = _resolve_optional_symbol(library, logical_name)
        functions[logical_name] = function
        if function is not None:
            function.argtypes = [handle]
            function.restype = uint32
            assert export_name is not None
            names[logical_name] = export_name

    bindings = NativeAudioCoreBindings(
        **functions,
        export_names=names,
    )
    actual_version = int(bindings.abi_version())
    if actual_version != AUDIO_CORE_ABI_VERSION:
        raise RuntimeError(
            "Unsupported SammyBlazeAudioCore ABI: "
            f"expected {AUDIO_CORE_ABI_VERSION}, found {actual_version}"
        )
    return bindings


def load_native_audio_core(
    explicit_path: str | os.PathLike[str] | None = None,
) -> tuple[object, NativeAudioCoreBindings, Path]:
    """Load and bind a native audio core from disk."""

    path = find_native_audio_core_library(explicit_path)
    assert path is not None
    try:
        library = ctypes.CDLL(str(path))
    except OSError as exc:
        raise RuntimeError(f"Could not load native audio core at {path}: {exc}") from exc
    return library, bind_native_audio_core(library), path


def patch_v1(
    preset: Preset,
    *,
    master_gain: float = 0.75,
    brightness: float = 0.5,
) -> SammyBlazeAudioPatchV1:
    """Convert a validated renderer-independent preset to ABI v1."""

    if not isinstance(preset, Preset):
        raise TypeError("preset must be a Preset")
    preset.validate()
    if not 0.0 <= float(master_gain) <= 1.0:
        raise ValueError("master_gain must be between 0 and 1")
    if not 0.0 <= float(brightness) <= 1.0:
        raise ValueError("brightness must be between 0 and 1")
    return SammyBlazeAudioPatchV1(
        struct_size=ctypes.sizeof(SammyBlazeAudioPatchV1),
        abi_version=AUDIO_CORE_ABI_VERSION,
        program=preset.program_id,
        waveform_a=WAVEFORM_ORDER.index(preset.waveform_a),
        waveform_b=WAVEFORM_ORDER.index(preset.waveform_b),
        filter_type=FILTER_TYPE_ORDER.index(preset.filter_type),
        unison_voices=preset.unison_voices,
        waveform_mix=float(preset.waveform_mix),
        attack_ms=float(preset.attack_ms),
        decay_ms=float(preset.decay_ms),
        sustain=float(preset.sustain),
        release_ms=float(preset.release_ms),
        filter_cutoff_hz=float(preset.filter_cutoff_hz),
        filter_resonance=float(preset.filter_resonance),
        filter_envelope=float(preset.filter_envelope),
        detune_cents=float(preset.detune_cents),
        vibrato_rate_hz=float(preset.vibrato_rate_hz),
        vibrato_depth_semitones=float(preset.vibrato_depth_semitones),
        reverb_mix=float(preset.reverb_mix),
        delay_mix=float(preset.delay_mix),
        delay_time_ms=float(preset.delay_time_ms),
        chorus_mix=float(preset.chorus_mix),
        master_gain=float(master_gain),
        brightness=float(brightness),
    )


class NativeAudioCoreOutput:
    """SoundDevice NoteSink backed by the versioned native C ABI.

    Control-thread calls only enqueue bounded events.  The SoundDevice callback
    is the sole owner of mutable DSP operations until the stream has stopped.
    """

    def __init__(
        self,
        program: int = 0,
        block_size: int = DEFAULT_BLOCK_SIZE,
        *,
        dll_path: str | os.PathLike[str] | None = None,
        sample_rate: float | None = None,
        device: int | str | None = None,
        event_queue_size: int = DEFAULT_EVENT_QUEUE_SIZE,
        report_queue_size: int = DEFAULT_REPORT_QUEUE_SIZE,
        max_events_per_callback: int = DEFAULT_MAX_EVENTS_PER_CALLBACK,
        timing_ring_capacity: int = DEFAULT_TIMING_RING_CAPACITY,
        callback_clock_ns: Callable[[], int] | None = None,
        library: object | None = None,
        sounddevice_module: object | None = None,
    ) -> None:
        if isinstance(block_size, bool) or not isinstance(block_size, int) or block_size <= 0:
            raise ValueError("block_size must be a positive integer")
        if (
            isinstance(event_queue_size, bool)
            or not isinstance(event_queue_size, int)
            or event_queue_size <= 0
        ):
            raise ValueError("event_queue_size must be a positive integer")
        if (
            isinstance(report_queue_size, bool)
            or not isinstance(report_queue_size, int)
            or report_queue_size <= 0
        ):
            raise ValueError("report_queue_size must be a positive integer")
        if (
            isinstance(max_events_per_callback, bool)
            or not isinstance(max_events_per_callback, int)
            or max_events_per_callback <= 0
        ):
            raise ValueError("max_events_per_callback must be a positive integer")
        if (
            isinstance(timing_ring_capacity, bool)
            or not isinstance(timing_ring_capacity, int)
            or timing_ring_capacity <= 0
        ):
            raise ValueError("timing_ring_capacity must be a positive integer")
        if isinstance(device, bool) or (
            device is not None
            and (
                not isinstance(device, (int, str))
                or (isinstance(device, int) and device < 0)
                or (isinstance(device, str) and not device.strip())
            )
        ):
            raise ValueError("device must be a non-negative index, non-empty name, or None")
        get_preset(program)

        self._events: Queue[tuple[str, object, object | None]] = Queue(
            maxsize=event_queue_size
        )
        self._callback_reports: Queue[str] = Queue(maxsize=report_queue_size)
        self._panic_pending = Event()
        self._max_events_per_callback = min(max_events_per_callback, event_queue_size)
        self._max_block_size = block_size
        self._callback_count = 0
        self._status_event_count = 0
        self._output_underflows = 0
        self._output_overflows = 0
        self._render_failures = 0
        self._event_queue_overflows = 0
        self._dropped_callback_reports = 0
        self._active_voice_count = 0
        self._requested_unison_voices: int | None = None
        self._rendered_unison_lanes_per_voice: int | None = None
        self._unison_quality_limited: bool | None = None
        self._last_unison_report: tuple[int, int, bool] | None = None
        self._nonfinite_recoveries = 0
        self._last_status: str | None = None
        self._last_error: str | None = None
        self._closed = False
        self._stream: Any | None = None
        self._handle = ctypes.c_void_p()
        self.output_device = device
        self._callback_clock_ns = callback_clock_ns or time.perf_counter_ns
        self._callback_timing_ring = (ctypes.c_uint64 * timing_ring_capacity)()
        self._callback_timing_capacity = timing_ring_capacity
        self._callback_timing_write_count = 0
        self._callback_deadline_miss_count = 0
        self._callback_timing_max_ns = 0
        self.output_device_index: int | None = None
        self.output_device_name: str | None = None
        self.output_host_api: str | None = None

        if library is None:
            loaded_library, api, loaded_path = load_native_audio_core(dll_path)
            self._library = loaded_library
            self._api = api
            self.library_path = str(loaded_path)
        else:
            self._library = library
            self._api = bind_native_audio_core(library)
            self.library_path = str(dll_path) if dll_path is not None else "<injected>"

        if sounddevice_module is None:
            try:
                import sounddevice as sounddevice_module
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "Install the [synth] extra to use native standalone audio"
                ) from exc

        try:
            device_info = sounddevice_module.query_devices(
                device=self.output_device,
                kind="output",
            )
            self.output_device_index = _optional_int(device_info.get("index"))
            self.output_device_name = _optional_text(device_info.get("name"))
            host_api_index = _optional_int(device_info.get("hostapi"))
            query_host_apis = getattr(sounddevice_module, "query_hostapis", None)
            if query_host_apis is not None and host_api_index is not None:
                host_api = query_host_apis(host_api_index)
                self.output_host_api = _optional_text(host_api.get("name"))
            if sample_rate is None:
                sample_rate = float(device_info["default_samplerate"])
            if not np.isfinite(sample_rate) or sample_rate <= 0:
                raise ValueError("sample_rate must be positive and finite")
            self.sample_rate = float(sample_rate)
            self._callback_deadline_ns = int(
                (self._max_block_size / self.sample_rate) * 1_000_000_000
            )
            created_handle = self._api.create(self.sample_rate, self._max_block_size)
            self._handle = (
                created_handle
                if isinstance(created_handle, ctypes.c_void_p)
                else ctypes.c_void_p(created_handle)
            )
            if not self._handle.value:
                raise RuntimeError("native audio core create returned a null handle")
            self._check_status(
                "program_change",
                self._api.program_change(self._handle, int(program)),
            )
            self._stream = sounddevice_module.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self._max_block_size,
                channels=STEREO_CHANNELS,
                dtype="float32",
                latency="low",
                callback=self._callback,
                device=self.output_device,
            )
            self._stream.start()
        except Exception as exc:
            self._close_failed_stream()
            self._destroy_native_handle()
            raise RuntimeError(f"Could not start the native audio output: {exc}") from exc

    @property
    def callback_health(self) -> NativeAudioCallbackHealth:
        return NativeAudioCallbackHealth(
            callback_count=self._callback_count,
            status_event_count=self._status_event_count,
            output_underflows=self._output_underflows,
            output_overflows=self._output_overflows,
            render_failures=self._render_failures,
            nonfinite_recoveries=self._nonfinite_recoveries,
            last_status=self._last_status,
            last_error=self._last_error,
            event_queue_overflows=self._event_queue_overflows,
            dropped_callback_reports=self._dropped_callback_reports,
            active_voice_count=self._active_voice_count,
            requested_unison_voices=self._requested_unison_voices,
            rendered_unison_lanes_per_voice=self._rendered_unison_lanes_per_voice,
            unison_quality_limited=self._unison_quality_limited,
            abi_version=AUDIO_CORE_ABI_VERSION,
            library_path=self.library_path,
            requested_output_device=self.output_device,
            output_device_index=self.output_device_index,
            output_device_name=self.output_device_name,
            output_host_api=self.output_host_api,
            sample_rate=self.sample_rate,
            block_size=self._max_block_size,
        )

    def drain_callback_reports(self) -> tuple[str, ...]:
        reports: list[str] = []
        while True:
            try:
                reports.append(self._callback_reports.get_nowait())
            except Empty:
                return tuple(reports)

    def callback_timing_snapshot(self) -> NativeAudioCallbackTiming:
        """Copy and summarize callback timings outside the real-time callback."""

        total = self._callback_timing_write_count
        retained = min(total, self._callback_timing_capacity)
        values = [
            int(self._callback_timing_ring[index])
            for index in range(retained)
        ]
        values.sort()
        return NativeAudioCallbackTiming(
            sample_count=total,
            retained_sample_count=retained,
            overwritten_sample_count=max(0, total - retained),
            ring_capacity=self._callback_timing_capacity,
            audio_deadline_ms=self._callback_deadline_ns / 1_000_000.0,
            deadline_miss_count=self._callback_deadline_miss_count,
            p50_ms=self._percentile_ms(values, 0.50),
            p95_ms=self._percentile_ms(values, 0.95),
            p99_ms=self._percentile_ms(values, 0.99),
            max_ms=(
                self._callback_timing_max_ns / 1_000_000.0
                if total
                else None
            ),
        )

    def note_on(self, note: int, velocity: int) -> None:
        self._validate_midi(note)
        self._validate_midi(velocity)
        self._enqueue(("note_on", note, velocity))

    def note_off(self, note: int) -> None:
        self._validate_midi(note)
        self._enqueue(("note_off", note, None))

    def control_change(self, control: int, value: int) -> None:
        self._validate_midi(control)
        self._validate_midi(value)
        self._enqueue(("cc", control, value))

    def program_change(self, program: int) -> None:
        preset = get_preset(program)
        self._enqueue(("program", preset.program_id, None))

    def apply_sound_patch(
        self,
        preset: Preset,
        *,
        master_gain: float = 0.75,
        brightness: float = 0.5,
    ) -> None:
        self._enqueue(
            (
                "patch",
                patch_v1(
                    preset,
                    master_gain=master_gain,
                    brightness=brightness,
                ),
                None,
            )
        )

    def panic(self) -> None:
        self._enqueue(("panic", 0, None))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception as exc:
                self._report(f"Audio stream stop failed: {type(exc).__name__}: {exc}")
            try:
                stream.close()
            except Exception as exc:
                self._report(f"Audio stream close failed: {type(exc).__name__}: {exc}")
        if self._handle.value:
            try:
                self._check_status("panic", self._api.panic(self._handle))
            except Exception as exc:
                self._report(f"Native panic failed during close: {type(exc).__name__}: {exc}")
        self._destroy_native_handle()

    def _enqueue(self, event: tuple[str, object, object | None]) -> None:
        if self._closed:
            return
        try:
            self._events.put_nowait(event)
        except Full:
            self._event_queue_overflows += 1
            self._panic_pending.set()
            self._report(
                "Native audio event queue overflow; pending events were discarded "
                "and a safety panic was requested"
            )

    def _callback(
        self,
        output: np.ndarray,
        frame_count: int,
        _time: object,
        status: object,
    ) -> None:
        started_ns = self._callback_clock_ns()
        try:
            self._render_callback(output, frame_count, _time, status)
        finally:
            elapsed_ns = self._callback_clock_ns() - started_ns
            if elapsed_ns < 0:
                elapsed_ns = 0
            write_count = self._callback_timing_write_count
            self._callback_timing_ring[
                write_count % self._callback_timing_capacity
            ] = elapsed_ns
            self._callback_timing_write_count = write_count + 1
            if elapsed_ns > self._callback_timing_max_ns:
                self._callback_timing_max_ns = elapsed_ns
            if elapsed_ns > self._callback_deadline_ns:
                self._callback_deadline_miss_count += 1

    def _render_callback(
        self,
        output: np.ndarray,
        frame_count: int,
        _time: object,
        status: object,
    ) -> None:
        try:
            self._callback_count += 1
            if status:
                status_text = str(status)
                self._status_event_count += 1
                self._output_underflows += int(
                    bool(getattr(status, "output_underflow", False))
                )
                self._output_overflows += int(
                    bool(getattr(status, "output_overflow", False))
                )
                if status_text != self._last_status:
                    self._report(f"Audio callback status: {status_text}")
                self._last_status = status_text

            if self._closed or not self._handle.value:
                output.fill(0.0)
                return
            if frame_count <= 0 or frame_count > self._max_block_size:
                raise ValueError(
                    f"callback frame count {frame_count} exceeds native maximum "
                    f"{self._max_block_size}"
                )
            if (
                output.dtype != np.float32
                or output.ndim != 2
                or output.shape[0] < frame_count
                or output.shape[1] != STEREO_CHANNELS
                or not output.flags.c_contiguous
            ):
                raise ValueError(
                    "native callback requires a contiguous float32 [frames, 2] buffer"
                )

            if self._panic_pending.is_set():
                self._discard_pending_events()
                self._check_status("panic", self._api.panic(self._handle))
                self._panic_pending.clear()

            for _ in range(self._max_events_per_callback):
                try:
                    event = self._events.get_nowait()
                except Empty:
                    break
                self._dispatch_event(event)

            pointer = output.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self._check_status(
                "render_interleaved",
                self._api.render_interleaved(self._handle, pointer, frame_count),
            )
            self._active_voice_count = int(self._api.active_voice_count(self._handle))
            self._update_unison_diagnostics()
            recovery_count = int(
                self._api.nonfinite_recovery_count(self._handle)
            )
            if recovery_count > self._nonfinite_recoveries:
                recovered = recovery_count - self._nonfinite_recoveries
                self._report(
                    "Native audio recovered from "
                    f"{recovered} new non-finite DSP event(s)"
                )
            self._nonfinite_recoveries = recovery_count
        except BaseException as exc:
            try:
                self._render_failures += 1
                error = f"{type(exc).__name__}: {exc}"
                if error != self._last_error:
                    self._report(f"Native audio callback failed: {error}")
                self._last_error = error
            except BaseException:
                pass
            try:
                output.fill(0.0)
            except BaseException:
                pass
            try:
                if self._handle.value:
                    self._check_status("panic", self._api.panic(self._handle))
            except BaseException as panic_exc:
                try:
                    self._report(
                        "Native safety panic failed: "
                        f"{type(panic_exc).__name__}: {panic_exc}"
                    )
                except BaseException:
                    pass

    def _update_unison_diagnostics(self) -> None:
        requested = self._api.requested_unison_voices
        rendered = self._api.rendered_unison_lanes_per_voice
        limited = self._api.unison_quality_limited
        if requested is None or rendered is None or limited is None:
            return

        self._requested_unison_voices = int(requested(self._handle))
        self._rendered_unison_lanes_per_voice = int(rendered(self._handle))
        self._unison_quality_limited = bool(limited(self._handle))
        snapshot = (
            self._requested_unison_voices,
            self._rendered_unison_lanes_per_voice,
            self._unison_quality_limited,
        )
        if snapshot == self._last_unison_report:
            return
        self._last_unison_report = snapshot
        if self._unison_quality_limited:
            self._report(
                "Native unison quality budget active: "
                f"requested {self._requested_unison_voices}, rendering "
                f"{self._rendered_unison_lanes_per_voice} lanes/voice"
            )
        else:
            self._report(
                "Native unison full quality: "
                f"{self._rendered_unison_lanes_per_voice} lanes/voice"
            )

    def _dispatch_event(self, event: tuple[str, object, object | None]) -> None:
        kind, data1, data2 = event
        if kind == "note_on":
            self._check_status(
                "note_on",
                self._api.note_on(
                    self._handle,
                    int(data1),
                    float(int(data2 or 0) / 127.0),
                ),
            )
        elif kind == "note_off":
            self._check_status(
                "note_off",
                self._api.note_off(self._handle, int(data1)),
            )
        elif kind == "cc":
            self._check_status(
                "control_change",
                self._api.control_change(self._handle, int(data1), int(data2 or 0)),
            )
        elif kind == "program":
            self._check_status(
                "program_change",
                self._api.program_change(self._handle, int(data1)),
            )
        elif kind == "patch" and isinstance(data1, SammyBlazeAudioPatchV1):
            self._check_status(
                "apply_patch",
                self._api.apply_patch(self._handle, ctypes.byref(data1)),
            )
        elif kind == "panic":
            self._check_status("panic", self._api.panic(self._handle))

    def _discard_pending_events(self) -> None:
        while True:
            try:
                self._events.get_nowait()
            except Empty:
                return

    def _report(self, message: str) -> None:
        try:
            self._callback_reports.put_nowait(message)
        except Full:
            self._dropped_callback_reports += 1

    def _destroy_native_handle(self) -> None:
        if not self._handle.value:
            return
        handle = self._handle
        self._handle = ctypes.c_void_p()
        try:
            self._api.destroy(handle)
        except Exception as exc:
            self._report(f"Native audio destroy failed: {type(exc).__name__}: {exc}")

    def _close_failed_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.close()
        except Exception:
            pass

    @staticmethod
    def _percentile_ms(values: list[int], quantile: float) -> float | None:
        if not values:
            return None
        if len(values) == 1:
            return values[0] / 1_000_000.0
        position = (len(values) - 1) * quantile
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(values) - 1)
        fraction = position - lower_index
        value = values[lower_index] + (
            values[upper_index] - values[lower_index]
        ) * fraction
        return value / 1_000_000.0

    @staticmethod
    def _check_status(operation: str, status: int) -> None:
        status_code = int(status)
        if status_code == 0:
            return
        description = _STATUS_NAMES.get(status_code, "unknown status")
        raise RuntimeError(
            f"native {operation} failed: {description} ({status_code})"
        )

    @staticmethod
    def _validate_midi(value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 127:
            raise ValueError("MIDI values must be integers between 0 and 127")


__all__ = [
    "AUDIO_CORE_ABI_VERSION",
    "DEFAULT_TIMING_RING_CAPACITY",
    "NativeAudioCallbackHealth",
    "NativeAudioCallbackTiming",
    "NativeAudioCoreBindings",
    "NativeAudioCoreOutput",
    "SammyBlazeAudioPatchV1",
    "bind_native_audio_core",
    "find_native_audio_core_library",
    "load_native_audio_core",
    "patch_v1",
]
