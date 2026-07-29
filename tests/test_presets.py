from dataclasses import FrozenInstanceError, fields, replace

import pytest

from handmusic.music.presets import (
    CATEGORIES,
    PRESETS,
    Preset,
    category_names,
    get_preset,
    get_preset_by_name,
    preset_names,
    presets_by_category,
    validate_catalog,
)


def test_catalog_has_at_least_one_hundred_production_presets() -> None:
    assert len(PRESETS) >= 100
    assert len(PRESETS) == 120


def test_program_ids_names_and_sound_designs_are_unique() -> None:
    assert len({preset.program_id for preset in PRESETS}) == len(PRESETS)
    assert len({preset.name.casefold() for preset in PRESETS}) == len(PRESETS)
    assert len({preset.synthesis_signature for preset in PRESETS}) == len(PRESETS)
    assert tuple(preset.program_id for preset in PRESETS) == tuple(range(len(PRESETS)))


def test_dataclass_fields_and_program_order_are_a_stable_integration_contract() -> None:
    assert tuple(field.name for field in fields(Preset)) == (
        "program_id",
        "midi_program",
        "category",
        "name",
        "waveform_a",
        "waveform_b",
        "waveform_mix",
        "attack_ms",
        "decay_ms",
        "sustain",
        "release_ms",
        "filter_type",
        "filter_cutoff_hz",
        "filter_resonance",
        "filter_envelope",
        "detune_cents",
        "unison_voices",
        "vibrato_rate_hz",
        "vibrato_depth_semitones",
        "reverb_mix",
        "delay_mix",
        "delay_time_ms",
        "chorus_mix",
    )
    assert tuple(PRESETS[offset].category for offset in range(0, 120, 12)) == CATEGORIES
    assert all(
        tuple(preset.program_id for preset in PRESETS[start : start + 12])
        == tuple(range(start, start + 12))
        for start in range(0, 120, 12)
    )


def test_every_requested_category_is_covered_with_a_deep_bank() -> None:
    expected = {
        "keys",
        "basses",
        "leads",
        "plucks",
        "bells",
        "polysynths",
        "pads",
        "atmospheres",
        "motion_textures",
        "cinematic",
    }

    assert set(category_names()) == expected
    assert set(CATEGORIES) == expected
    assert all(len(presets_by_category(category)) >= 10 for category in expected)


@pytest.mark.parametrize("preset", PRESETS)
def test_all_parameters_are_renderer_safe_and_bounded(preset: Preset) -> None:
    preset.validate()
    assert 0 <= preset.midi_program <= 127
    assert 0.0 <= preset.waveform_mix <= 1.0
    assert 0.0 <= preset.attack_ms <= 20_000.0
    assert 0.0 <= preset.decay_ms <= 20_000.0
    assert 0.0 <= preset.sustain <= 1.0
    assert 0.0 <= preset.release_ms <= 30_000.0
    assert 20.0 <= preset.filter_cutoff_hz <= 20_000.0
    assert 0.0 <= preset.filter_resonance <= 1.0
    assert -1.0 <= preset.filter_envelope <= 1.0
    assert 0.0 <= preset.detune_cents <= 100.0
    assert 1 <= preset.unison_voices <= 16
    assert 0.0 <= preset.vibrato_rate_hz <= 15.0
    assert 0.0 <= preset.vibrato_depth_semitones <= 2.0
    assert 0.0 <= preset.reverb_mix <= 1.0
    assert 0.0 <= preset.delay_mix <= 1.0
    assert 1.0 <= preset.delay_time_ms <= 2_500.0
    assert 0.0 <= preset.chorus_mix <= 1.0


def test_lookup_is_deterministic_by_id_name_and_normalized_name() -> None:
    preset = get_preset(0)

    assert preset is get_preset(0)
    assert preset is get_preset_by_name(preset.name)
    assert preset is get_preset_by_name("  STUDIO-grand ")
    assert preset_names("key")[0] == preset.name
    assert presets_by_category("motion texture") == presets_by_category("motion_textures")


def test_preset_is_frozen_and_exposes_convenient_renderer_values() -> None:
    preset = PRESETS[0]

    assert preset.waveform == f"{preset.waveform_a}/{preset.waveform_b}"
    assert preset.adsr == (
        preset.attack_ms,
        preset.decay_ms,
        preset.sustain,
        preset.release_ms,
    )
    with pytest.raises(FrozenInstanceError):
        preset.name = "Mutable"  # type: ignore[misc]


def test_catalog_validation_rejects_duplicate_identity_and_aliases() -> None:
    original = PRESETS[0]

    with pytest.raises(ValueError, match="program IDs"):
        validate_catalog((original, replace(PRESETS[1], program_id=original.program_id)))
    with pytest.raises(ValueError, match="names"):
        validate_catalog((original, replace(PRESETS[1], name=original.name)))
    with pytest.raises(ValueError, match="alias"):
        validate_catalog(
            (
                original,
                replace(
                    original,
                    program_id=16_000,
                    name="Different Label, Same Sound",
                ),
            )
        )


def test_invalid_lookup_and_parameters_fail_clearly() -> None:
    with pytest.raises(KeyError, match="program ID"):
        get_preset(99_999)
    with pytest.raises(KeyError, match="preset name"):
        get_preset_by_name("Not A Real Patch")
    with pytest.raises(KeyError, match="category"):
        presets_by_category("woodwinds")
    with pytest.raises(ValueError, match="filter_cutoff_hz"):
        replace(PRESETS[0], filter_cutoff_hz=21_000.0)
    with pytest.raises(ValueError, match="midi_program"):
        replace(PRESETS[0], midi_program=128)
