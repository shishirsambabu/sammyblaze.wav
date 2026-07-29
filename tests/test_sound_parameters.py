import pytest

from handmusic.music.presets import get_preset
from handmusic.music.sound_parameters import (
    SoundParameter,
    encode_sound_parameter,
    patch_messages,
)


def test_complete_patch_uses_stable_parameter_order() -> None:
    messages = patch_messages(get_preset(83), master_gain=0.8, brightness=0.4)

    assert tuple(parameter for parameter, _ in messages) == tuple(SoundParameter)
    assert all(0 <= value <= 127 for _, value in messages)


def test_discrete_sound_parameters_encode_endpoints() -> None:
    assert encode_sound_parameter(SoundParameter.WAVEFORM_A, "sine") == 0
    assert encode_sound_parameter(SoundParameter.WAVEFORM_A, "wavetable") == 127
    assert encode_sound_parameter(SoundParameter.FILTER_TYPE, "lowpass") == 0
    assert encode_sound_parameter(SoundParameter.FILTER_TYPE, "notch") == 127


def test_logarithmic_parameters_are_monotonic() -> None:
    values = [
        encode_sound_parameter(SoundParameter.FILTER_CUTOFF_HZ, cutoff)
        for cutoff in (20, 100, 1000, 10_000, 20_000)
    ]

    assert values == sorted(values)
    assert values[0] == 0
    assert values[-1] == 127


@pytest.mark.parametrize(
    ("parameter", "value"),
    (
        (SoundParameter.WAVEFORM_A, "supersaw"),
        (SoundParameter.FILTER_TYPE, "comb"),
    ),
)
def test_invalid_discrete_values_are_rejected(
    parameter: SoundParameter,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        encode_sound_parameter(parameter, value)
