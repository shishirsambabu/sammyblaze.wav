from __future__ import annotations

from enum import IntEnum
from math import log

from handmusic.music.presets import Preset

WAVEFORM_ORDER = (
    "sine",
    "triangle",
    "saw",
    "square",
    "pulse",
    "organ",
    "metal",
    "noise",
    "vocal",
    "wavetable",
)
FILTER_TYPE_ORDER = ("lowpass", "highpass", "bandpass", "notch")


class SoundParameter(IntEnum):
    MASTER_GAIN = 0
    WAVEFORM_A = 1
    WAVEFORM_B = 2
    WAVEFORM_MIX = 3
    ATTACK_MS = 4
    DECAY_MS = 5
    SUSTAIN = 6
    RELEASE_MS = 7
    FILTER_TYPE = 8
    FILTER_CUTOFF_HZ = 9
    FILTER_RESONANCE = 10
    FILTER_ENVELOPE = 11
    DETUNE_CENTS = 12
    UNISON_VOICES = 13
    VIBRATO_RATE_HZ = 14
    VIBRATO_DEPTH_SEMITONES = 15
    REVERB_MIX = 16
    DELAY_MIX = 17
    DELAY_TIME_MS = 18
    CHORUS_MIX = 19
    BRIGHTNESS = 20


def _linear(value: float, minimum: float, maximum: float) -> int:
    normalized = (float(value) - minimum) / (maximum - minimum)
    return round(max(0.0, min(1.0, normalized)) * 127.0)


def _logarithmic(value: float, minimum: float, maximum: float) -> int:
    bounded = max(minimum, min(maximum, float(value)))
    normalized = log(bounded / minimum) / log(maximum / minimum)
    return round(normalized * 127.0)


def encode_sound_parameter(parameter: SoundParameter, value: object) -> int:
    """Encode one editable sound value into the bridge's seven-bit payload."""

    if parameter in (SoundParameter.WAVEFORM_A, SoundParameter.WAVEFORM_B):
        try:
            index = WAVEFORM_ORDER.index(str(value))
        except ValueError:
            raise ValueError(f"unsupported waveform: {value!r}") from None
        return round(index * 127 / (len(WAVEFORM_ORDER) - 1))
    if parameter is SoundParameter.FILTER_TYPE:
        try:
            index = FILTER_TYPE_ORDER.index(str(value))
        except ValueError:
            raise ValueError(f"unsupported filter type: {value!r}") from None
        return round(index * 127 / (len(FILTER_TYPE_ORDER) - 1))
    if parameter is SoundParameter.ATTACK_MS:
        return 0 if float(value) <= 0 else _logarithmic(float(value), 0.5, 20_000.0)
    if parameter is SoundParameter.DECAY_MS:
        return _logarithmic(float(value), 0.5, 20_000.0)
    if parameter is SoundParameter.RELEASE_MS:
        return 0 if float(value) <= 0 else _logarithmic(float(value), 0.5, 30_000.0)
    if parameter is SoundParameter.FILTER_CUTOFF_HZ:
        return _logarithmic(float(value), 20.0, 20_000.0)
    if parameter is SoundParameter.DELAY_TIME_MS:
        return _logarithmic(float(value), 1.0, 2_500.0)

    ranges = {
        SoundParameter.MASTER_GAIN: (0.0, 1.0),
        SoundParameter.WAVEFORM_MIX: (0.0, 1.0),
        SoundParameter.SUSTAIN: (0.0, 1.0),
        SoundParameter.FILTER_RESONANCE: (0.0, 1.0),
        SoundParameter.FILTER_ENVELOPE: (-1.0, 1.0),
        SoundParameter.DETUNE_CENTS: (0.0, 100.0),
        SoundParameter.UNISON_VOICES: (1.0, 16.0),
        SoundParameter.VIBRATO_RATE_HZ: (0.0, 15.0),
        SoundParameter.VIBRATO_DEPTH_SEMITONES: (0.0, 2.0),
        SoundParameter.REVERB_MIX: (0.0, 1.0),
        SoundParameter.DELAY_MIX: (0.0, 1.0),
        SoundParameter.CHORUS_MIX: (0.0, 1.0),
        SoundParameter.BRIGHTNESS: (0.0, 1.0),
    }
    try:
        minimum, maximum = ranges[parameter]
    except KeyError:
        raise ValueError(f"unsupported sound parameter: {parameter!r}") from None
    return _linear(float(value), minimum, maximum)


def patch_messages(
    preset: Preset,
    *,
    master_gain: float = 0.75,
    brightness: float = 0.5,
) -> tuple[tuple[SoundParameter, int], ...]:
    """Return a complete, stable parameter snapshot for standalone/VST parity."""

    values: tuple[tuple[SoundParameter, object], ...] = (
        (SoundParameter.MASTER_GAIN, master_gain),
        (SoundParameter.WAVEFORM_A, preset.waveform_a),
        (SoundParameter.WAVEFORM_B, preset.waveform_b),
        (SoundParameter.WAVEFORM_MIX, preset.waveform_mix),
        (SoundParameter.ATTACK_MS, preset.attack_ms),
        (SoundParameter.DECAY_MS, preset.decay_ms),
        (SoundParameter.SUSTAIN, preset.sustain),
        (SoundParameter.RELEASE_MS, preset.release_ms),
        (SoundParameter.FILTER_TYPE, preset.filter_type),
        (SoundParameter.FILTER_CUTOFF_HZ, preset.filter_cutoff_hz),
        (SoundParameter.FILTER_RESONANCE, preset.filter_resonance),
        (SoundParameter.FILTER_ENVELOPE, preset.filter_envelope),
        (SoundParameter.DETUNE_CENTS, preset.detune_cents),
        (SoundParameter.UNISON_VOICES, preset.unison_voices),
        (SoundParameter.VIBRATO_RATE_HZ, preset.vibrato_rate_hz),
        (SoundParameter.VIBRATO_DEPTH_SEMITONES, preset.vibrato_depth_semitones),
        (SoundParameter.REVERB_MIX, preset.reverb_mix),
        (SoundParameter.DELAY_MIX, preset.delay_mix),
        (SoundParameter.DELAY_TIME_MS, preset.delay_time_ms),
        (SoundParameter.CHORUS_MIX, preset.chorus_mix),
        (SoundParameter.BRIGHTNESS, brightness),
    )
    return tuple(
        (parameter, encode_sound_parameter(parameter, value)) for parameter, value in values
    )


__all__ = [
    "FILTER_TYPE_ORDER",
    "SoundParameter",
    "WAVEFORM_ORDER",
    "encode_sound_parameter",
    "patch_messages",
]
