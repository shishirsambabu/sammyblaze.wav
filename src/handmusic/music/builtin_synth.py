from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, pi, sin, tan
from queue import SimpleQueue
from typing import Any

import numpy as np

from handmusic.music.presets import Preset, get_preset

_MAX_VOICES = 24
_MAX_UNISON = 3
_MIN_TIME_MS = 0.5
_MAX_FILTER_STATE = 1_000_000.0


@dataclass(frozen=True, slots=True)
class AudioCallbackHealth:
    """Thread-safe snapshot of failures observed by the audio callback."""

    callback_count: int
    status_event_count: int
    output_underflows: int
    output_overflows: int
    render_failures: int
    nonfinite_recoveries: int
    last_status: str | None
    last_error: str | None

    @property
    def healthy(self) -> bool:
        return not (
            self.status_event_count
            or self.render_failures
            or self.nonfinite_recoveries
        )


@dataclass(slots=True)
class _Voice:
    note: int
    velocity: float
    preset: Preset
    age: int
    phase_a: np.ndarray = field(default_factory=lambda: np.zeros(_MAX_UNISON))
    phase_b: np.ndarray = field(default_factory=lambda: np.full(_MAX_UNISON, 0.173))
    envelope: float = 0.0
    stage: str = "attack"
    release_step: float = 0.0
    filter_low: float = 0.0
    filter_band: float = 0.0
    key_down: bool = True


class SynthEngine:
    """Deterministic polyphonic renderer used by the direct desktop audio output."""

    def __init__(self, sample_rate: float = 48_000.0, program: int = 0) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self.sample_rate = float(sample_rate)
        self.preset = get_preset(program)
        self.voices: list[_Voice] = []
        self.master_gain = 0.75
        self.expression = 1.0
        self.brightness = 0.5
        self.gesture_vibrato = 0.25
        self.reverb_mix = self.preset.reverb_mix
        self.delay_mix = self.preset.delay_mix
        self.chorus_mix = self.preset.chorus_mix
        self.sustain_enabled = False
        self._age = 0
        self._lfo_phase = 0.0
        self._effect_buffer = np.zeros(int(self.sample_rate * 2.6), dtype=np.float64)
        self._effect_index = 0
        self._rng = np.random.default_rng(0x5A4D4D59)
        self.nonfinite_recoveries = 0
        self.last_render_error: str | None = None

    def note_on(self, note: int, velocity: int) -> None:
        self._validate_midi(note)
        self._validate_midi(velocity)
        self._age += 1
        if len(self.voices) >= _MAX_VOICES:
            victim = min(
                self.voices,
                key=lambda voice: (
                    voice.stage != "release",
                    voice.envelope,
                    voice.age,
                ),
            )
            self.voices.remove(victim)
        self.voices.append(
            _Voice(
                note=note,
                velocity=velocity / 127.0,
                preset=self.preset,
                age=self._age,
            )
        )

    def note_off(self, note: int) -> None:
        self._validate_midi(note)
        for voice in self.voices:
            if voice.note == note:
                voice.key_down = False
                if not self.sustain_enabled:
                    self._begin_release(voice)

    def control_change(self, control: int, value: int) -> None:
        self._validate_midi(control)
        self._validate_midi(value)
        normalized = value / 127.0
        if control == 1:
            self.gesture_vibrato = normalized
        elif control == 7:
            self.master_gain = normalized
        elif control == 11:
            self.expression = normalized
        elif control == 64:
            self._set_sustain(value >= 64)
        elif control == 74:
            self.brightness = normalized
        elif control == 91:
            self.reverb_mix = normalized
        elif control == 93:
            self.chorus_mix = normalized
        elif control == 94:
            self.delay_mix = normalized
        elif control in (120, 123):
            self.panic()

    def program_change(self, program: int) -> None:
        self.apply_sound_patch(get_preset(program))
        self.panic()

    def apply_sound_patch(
        self,
        preset: Preset,
        *,
        master_gain: float | None = None,
        brightness: float | None = None,
    ) -> None:
        """Apply a full Moog-style patch without interrupting active voices."""

        preset.validate()
        if master_gain is not None and not 0.0 <= master_gain <= 1.0:
            raise ValueError("master_gain must be between 0 and 1")
        if brightness is not None and not 0.0 <= brightness <= 1.0:
            raise ValueError("brightness must be between 0 and 1")
        self.preset = preset
        for voice in self.voices:
            voice.preset = preset
        self.reverb_mix = preset.reverb_mix
        self.delay_mix = preset.delay_mix
        self.chorus_mix = preset.chorus_mix
        if master_gain is not None:
            self.master_gain = master_gain
        if brightness is not None:
            self.brightness = brightness

    def panic(self) -> None:
        self.voices.clear()
        self.sustain_enabled = False
        self._effect_buffer.fill(0.0)
        self._effect_index = 0

    def render(self, frame_count: int) -> np.ndarray:
        """Render one stereo block without touching hardware."""

        if frame_count <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        mono = np.zeros(frame_count, dtype=np.float64)
        finished: list[_Voice] = []
        for voice in tuple(self.voices):
            rendered = self._render_voice(voice, frame_count)
            mono += rendered
            if voice.stage == "off":
                finished.append(voice)
        self._lfo_phase = (
            self._lfo_phase
            + frame_count * max(0.01, self.preset.vibrato_rate_hz) / self.sample_rate
        ) % 1.0
        for voice in finished:
            if voice in self.voices:
                self.voices.remove(voice)

        mono *= self.master_gain * self.expression * 0.13
        output = self._apply_effects(mono)
        limited = np.tanh(output * 1.15) * 0.86
        if not np.isfinite(limited).all():
            self._record_nonfinite_recovery(
                "Non-finite samples reached the synth output boundary"
            )
            limited = np.nan_to_num(limited, nan=0.0, posinf=0.86, neginf=-0.86)
            self._effect_buffer.fill(0.0)
            for voice in self.voices:
                voice.filter_low = 0.0
                voice.filter_band = 0.0
        return limited.astype(np.float32, copy=False)

    def _render_voice(self, voice: _Voice, frame_count: int) -> np.ndarray:
        envelope = self._render_envelope(voice, frame_count)
        if voice.stage == "off" and not np.any(envelope):
            return np.zeros(frame_count)

        preset = voice.preset
        samples = np.arange(frame_count, dtype=np.float64)
        vibrato_rate = max(0.01, preset.vibrato_rate_hz)
        lfo = np.sin(2.0 * pi * (self._lfo_phase + samples * vibrato_rate / self.sample_rate))
        vibrato_depth = preset.vibrato_depth_semitones + self.gesture_vibrato * 0.5
        frequency = 440.0 * np.power(
            2.0,
            ((voice.note - 69.0) + lfo * vibrato_depth) / 12.0,
        )
        unison = min(_MAX_UNISON, max(1, preset.unison_voices))
        oscillators = np.zeros(frame_count, dtype=np.float64)
        center = (unison - 1) / 2.0
        denominator = max(1.0, center)
        for index in range(unison):
            detune = (index - center) * preset.detune_cents / denominator
            increment = np.minimum(
                frequency * (2.0 ** (detune / 1200.0)) / self.sample_rate,
                0.45,
            )
            phase_a = (voice.phase_a[index] + np.cumsum(increment)) % 1.0
            phase_b = (voice.phase_b[index] + np.cumsum(increment * 1.001)) % 1.0
            voice.phase_a[index] = phase_a[-1]
            voice.phase_b[index] = phase_b[-1]
            wave_a = self._wave(preset.waveform_a, phase_a)
            wave_b = self._wave(preset.waveform_b, phase_b)
            oscillators += wave_a * (1.0 - preset.waveform_mix) + wave_b * preset.waveform_mix
        oscillators /= np.sqrt(float(unison))
        oscillators *= envelope * voice.velocity
        return self._filter(voice, oscillators, envelope)

    def _render_envelope(self, voice: _Voice, frame_count: int) -> np.ndarray:
        values = np.empty(frame_count, dtype=np.float64)
        preset = voice.preset
        for index in range(frame_count):
            if voice.stage == "attack":
                voice.envelope += 1000.0 / (max(preset.attack_ms, _MIN_TIME_MS) * self.sample_rate)
                if voice.envelope >= 1.0:
                    voice.envelope = 1.0
                    voice.stage = "decay"
            elif voice.stage == "decay":
                voice.envelope -= (
                    (1.0 - preset.sustain)
                    * 1000.0
                    / (max(preset.decay_ms, _MIN_TIME_MS) * self.sample_rate)
                )
                if voice.envelope <= preset.sustain:
                    voice.envelope = preset.sustain
                    voice.stage = "sustain"
            elif voice.stage == "sustain":
                voice.envelope = preset.sustain
            elif voice.stage == "release":
                voice.envelope -= voice.release_step
                if voice.envelope <= 0.0001:
                    voice.envelope = 0.0
                    voice.stage = "off"
            else:
                voice.envelope = 0.0
            values[index] = voice.envelope
        return values

    def _filter(
        self,
        voice: _Voice,
        signal: np.ndarray,
        envelope: np.ndarray,
    ) -> np.ndarray:
        preset = voice.preset
        output = np.empty_like(signal)
        resonance = max(0.0, min(float(preset.filter_resonance), 1.0))
        quality = 0.5 * (16.0**resonance)
        damping = 1.0 / quality
        brightness_octaves = (self.brightness - 0.5) * 4.0
        integrator_low = float(voice.filter_low)
        integrator_band = float(voice.filter_band)
        if not self._filter_state_is_valid(integrator_low, integrator_band):
            self._record_nonfinite_recovery("Invalid filter state reset before rendering")
            integrator_low = 0.0
            integrator_band = 0.0

        for index, sample_value in enumerate(signal):
            sample = float(sample_value)
            if not isfinite(sample):
                self._record_nonfinite_recovery("Non-finite oscillator sample rejected")
                sample = 0.0
            cutoff = max(
                25.0,
                min(
                    preset.filter_cutoff_hz
                    * 2.0
                    ** (preset.filter_envelope * float(envelope[index]) * 4.0 + brightness_octaves),
                    self.sample_rate * 0.42,
                ),
            )
            coefficient = tan(pi * cutoff / self.sample_rate)
            denominator = 1.0 + coefficient * (coefficient + damping)
            a1 = 1.0 / denominator
            a2 = coefficient * a1
            a3 = coefficient * a2
            input_minus_low = sample - integrator_low
            band = a1 * integrator_band + a2 * input_minus_low
            low = integrator_low + a2 * integrator_band + a3 * input_minus_low
            high = sample - damping * band - low
            next_band = 2.0 * band - integrator_band
            next_low = 2.0 * low - integrator_low
            if not self._filter_state_is_valid(next_low, next_band):
                self._record_nonfinite_recovery("Unstable filter state reset while rendering")
                integrator_low = 0.0
                integrator_band = 0.0
                output[index] = 0.0
                continue
            integrator_low = next_low
            integrator_band = next_band
            if preset.filter_type == "lowpass":
                output[index] = low
            elif preset.filter_type == "highpass":
                output[index] = high
            elif preset.filter_type == "bandpass":
                output[index] = band
            else:
                output[index] = low + high
        voice.filter_low = integrator_low
        voice.filter_band = integrator_band
        return output

    @staticmethod
    def _filter_state_is_valid(low: float, band: float) -> bool:
        return (
            isfinite(low)
            and isfinite(band)
            and abs(low) <= _MAX_FILTER_STATE
            and abs(band) <= _MAX_FILTER_STATE
        )

    def _record_nonfinite_recovery(self, message: str) -> None:
        self.nonfinite_recoveries += 1
        self.last_render_error = message

    def _apply_effects(self, mono: np.ndarray) -> np.ndarray:
        stereo = np.empty((len(mono), 2), dtype=np.float64)
        size = len(self._effect_buffer)
        delay_samples = int(
            max(
                1,
                min(
                    self.preset.delay_time_ms * self.sample_rate / 1000.0,
                    size - 1,
                ),
            )
        )
        reverb_a = max(1, int(self.sample_rate * 0.061))
        reverb_b = max(1, int(self.sample_rate * 0.089))
        for index, dry in enumerate(mono):
            phase = (self._lfo_phase + index * 0.73 / self.sample_rate) % 1.0
            chorus_samples = max(
                1,
                int(self.sample_rate * (0.018 + 0.005 * (0.5 + 0.5 * sin(2 * pi * phase)))),
            )
            delay = self._tap(delay_samples)
            room_a = self._tap(reverb_a)
            room_b = self._tap(reverb_b)
            chorus = self._tap(chorus_samples)
            self._effect_buffer[self._effect_index] = max(
                -2.0,
                min(
                    dry
                    + delay * self.delay_mix * 0.42
                    + (room_a + room_b) * self.reverb_mix * 0.24,
                    2.0,
                ),
            )
            self._effect_index = (self._effect_index + 1) % size
            stereo[index, 0] = (
                dry
                + delay * self.delay_mix * 0.62
                + room_a * self.reverb_mix * 0.48
                + chorus * self.chorus_mix * 0.34
            )
            stereo[index, 1] = (
                dry
                + delay * self.delay_mix * 0.48
                + room_b * self.reverb_mix * 0.48
                - chorus * self.chorus_mix * 0.28
            )
        return stereo

    def _tap(self, samples_back: int) -> float:
        return float(
            self._effect_buffer[
                (self._effect_index + len(self._effect_buffer) - samples_back)
                % len(self._effect_buffer)
            ]
        )

    def _wave(self, waveform: str, phase: np.ndarray) -> np.ndarray:
        angle = phase * 2.0 * pi
        if waveform == "sine":
            return np.sin(angle)
        if waveform == "triangle":
            return (2.0 / pi) * np.arcsin(np.sin(angle))
        if waveform == "saw":
            return phase * 2.0 - 1.0
        if waveform == "square":
            return np.where(phase < 0.5, 1.0, -1.0)
        if waveform == "pulse":
            return np.where(phase < 0.28, 1.0, -1.0)
        if waveform == "organ":
            return np.sin(angle) * 0.68 + np.sin(angle * 2.0) * 0.22 + np.sin(angle * 3.0) * 0.10
        if waveform == "metal":
            return np.sin(angle) * 0.52 + np.sin(angle * 2.41) * 0.30 + np.sin(angle * 5.31) * 0.18
        if waveform == "noise":
            return self._rng.uniform(-1.0, 1.0, len(phase))
        if waveform == "vocal":
            return np.sin(angle) * 0.58 + np.sin(angle * 2.0) * 0.27 + np.sin(angle * 4.0) * 0.15
        return np.sin(angle) * 0.62 + np.sin(angle * 3.0) * 0.23 + (phase * 2.0 - 1.0) * 0.15

    def _begin_release(self, voice: _Voice) -> None:
        if voice.stage in ("off", "release"):
            return
        release_samples = max(
            1.0,
            max(voice.preset.release_ms, _MIN_TIME_MS) * self.sample_rate / 1000.0,
        )
        voice.release_step = voice.envelope / release_samples
        voice.stage = "release"

    def _set_sustain(self, enabled: bool) -> None:
        if self.sustain_enabled == enabled:
            return
        self.sustain_enabled = enabled
        if not enabled:
            for voice in self.voices:
                if not voice.key_down:
                    self._begin_release(voice)

    @staticmethod
    def _validate_midi(value: int) -> None:
        if not isinstance(value, int) or not 0 <= value <= 127:
            raise ValueError("MIDI values must be integers between 0 and 127")


class BuiltinSynthOutput:
    """Low-latency SoundDevice adapter for the 120-sound factory engine."""

    def __init__(self, program: int = 0, block_size: int = 256) -> None:
        try:
            import sounddevice
        except ImportError as exc:  # pragma: no cover - optional native adapter
            raise RuntimeError(
                "Install the [synth] extra to use the built-in audio engine"
            ) from exc
        try:
            device = sounddevice.query_devices(kind="output")
            sample_rate = float(device["default_samplerate"])
            self._engine = SynthEngine(sample_rate, program)
            self._events: SimpleQueue[tuple[str, object, object | None]] = SimpleQueue()
            self._callback_reports: SimpleQueue[str] = SimpleQueue()
            self._callback_count = 0
            self._status_event_count = 0
            self._output_underflows = 0
            self._output_overflows = 0
            self._render_failures = 0
            self._reported_nonfinite_recoveries = 0
            self._last_status: str | None = None
            self._last_error: str | None = None
            self._closed = False
            self._stream: Any = sounddevice.OutputStream(
                samplerate=sample_rate,
                blocksize=block_size,
                channels=2,
                dtype="float32",
                latency="low",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            raise RuntimeError(f"Could not start the built-in audio output: {exc}") from exc

    @property
    def callback_health(self) -> AudioCallbackHealth:
        """Return callback diagnostics without blocking or touching the stream."""

        return AudioCallbackHealth(
            callback_count=self._callback_count,
            status_event_count=self._status_event_count,
            output_underflows=self._output_underflows,
            output_overflows=self._output_overflows,
            render_failures=self._render_failures,
            nonfinite_recoveries=self._reported_nonfinite_recoveries,
            last_status=self._last_status,
            last_error=self._last_error,
        )

    def drain_callback_reports(self) -> tuple[str, ...]:
        """Return new callback warnings/errors accumulated since the last drain."""

        reports: list[str] = []
        while not self._callback_reports.empty():
            reports.append(self._callback_reports.get_nowait())
        return tuple(reports)

    def note_on(self, note: int, velocity: int) -> None:
        self._events.put(("note_on", note, velocity))

    def note_off(self, note: int) -> None:
        self._events.put(("note_off", note, None))

    def control_change(self, control: int, value: int) -> None:
        self._events.put(("cc", control, value))

    def program_change(self, program: int) -> None:
        get_preset(program)
        self._events.put(("program", program, None))

    def apply_sound_patch(
        self,
        preset: Preset,
        *,
        master_gain: float = 0.75,
        brightness: float = 0.5,
    ) -> None:
        preset.validate()
        self._events.put(("patch", preset, (master_gain, brightness)))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._engine.panic()
        self._stream.stop()
        self._stream.close()

    def _callback(
        self,
        output: np.ndarray,
        frame_count: int,
        _time: object,
        _status: object,
    ) -> None:
        self._callback_count += 1
        if _status:
            status_text = str(_status)
            self._status_event_count += 1
            self._output_underflows += int(
                bool(getattr(_status, "output_underflow", False))
            )
            self._output_overflows += int(
                bool(getattr(_status, "output_overflow", False))
            )
            if status_text != self._last_status:
                self._callback_reports.put(f"Audio callback status: {status_text}")
            self._last_status = status_text
        try:
            while not self._events.empty():
                kind, data1, data2 = self._events.get_nowait()
                if kind == "note_on":
                    self._engine.note_on(int(data1), int(data2 or 0))
                elif kind == "note_off":
                    self._engine.note_off(int(data1))
                elif kind == "cc":
                    self._engine.control_change(int(data1), int(data2 or 0))
                elif kind == "patch":
                    if not isinstance(data1, Preset) or not isinstance(data2, tuple):
                        continue
                    master_gain, brightness = data2
                    self._engine.apply_sound_patch(
                        data1,
                        master_gain=float(master_gain),
                        brightness=float(brightness),
                    )
                else:
                    self._engine.program_change(int(data1))
            output[:] = self._engine.render(frame_count)
            recoveries = (
                self._engine.nonfinite_recoveries
                - self._reported_nonfinite_recoveries
            )
            if recoveries > 0:
                self._reported_nonfinite_recoveries += recoveries
                message = self._engine.last_render_error or "Unknown numerical recovery"
                self._callback_reports.put(
                    f"Audio render recovered from {recoveries} non-finite event(s): "
                    f"{message}"
                )
        except Exception as exc:
            self._render_failures += 1
            error = f"{type(exc).__name__}: {exc}"
            if error != self._last_error:
                self._callback_reports.put(f"Audio render failed: {error}")
            self._last_error = error
            output.fill(0.0)


__all__ = ["AudioCallbackHealth", "BuiltinSynthOutput", "SynthEngine"]
