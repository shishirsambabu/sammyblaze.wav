import json
from dataclasses import fields
from pathlib import Path

import pytest

from handmusic.music.presets import Preset, get_preset
from handmusic.music.user_presets import (
    USER_PRESET_SCHEMA_VERSION,
    InvalidUserPresetError,
    UnsupportedUserPresetVersionError,
    UserPreset,
    default_preset_directory,
    delete_user_preset,
    list_user_presets,
    load_user_preset,
    preset_filename,
    save_user_preset,
)


def _edited_preset(name: str = "My Wide Pad") -> UserPreset:
    return UserPreset.from_factory(
        72,
        name,
        master_gain=0.67,
        brightness=0.81,
        waveform_mix=0.73,
        attack_ms=1_234.0,
        release_ms=4_321.0,
        filter_cutoff_hz=3_456.0,
        filter_resonance=0.44,
        reverb_mix=0.62,
        delay_mix=0.31,
        delay_time_ms=487.0,
        chorus_mix=0.55,
    )


def test_round_trip_preserves_full_patch_gain_brightness_and_provenance(
    tmp_path: Path,
) -> None:
    preset = _edited_preset()

    saved_path = save_user_preset(preset, directory=tmp_path)
    loaded = load_user_preset("my wide pad", directory=tmp_path)

    assert loaded == preset
    assert loaded.patch == preset.patch
    assert loaded.source_factory_program_id == 72
    assert loaded.master_gain == 0.67
    assert loaded.brightness == 0.81
    assert saved_path.name == preset_filename(preset.custom_name)
    assert saved_path.parent == tmp_path

    document = json.loads(saved_path.read_text(encoding="utf-8"))
    assert document["schema_version"] == USER_PRESET_SCHEMA_VERSION
    assert set(document["patch"]) == {field.name for field in fields(Preset)}
    assert document["master_gain"] == 0.67
    assert document["brightness"] == 0.81


def test_factory_creation_is_validated_by_preset_and_control_bounds() -> None:
    with pytest.raises(ValueError, match="filter_cutoff_hz"):
        UserPreset.from_factory(0, "Unsafe Cutoff", filter_cutoff_hz=20_001.0)
    with pytest.raises(ValueError, match="master_gain"):
        UserPreset.from_factory(0, "Unsafe Gain", master_gain=1.01)
    with pytest.raises(ValueError, match="brightness"):
        UserPreset.from_factory(0, "Unsafe Brightness", brightness=-0.01)
    with pytest.raises(TypeError, match="brightness"):
        UserPreset.from_factory(0, "Boolean Brightness", brightness=True)
    with pytest.raises(ValueError, match="factory preset"):
        UserPreset.from_factory(16_000, "Missing Factory")


@pytest.mark.parametrize(
    "bad_name",
    (
        "",
        "   ",
        ".",
        "..",
        "../outside",
        r"..\outside",
        "folder/name",
        r"folder\name",
        "bad:name",
        "CON",
        "LPT9.txt",
        "control\x00name",
    ),
)
def test_name_validation_and_traversal_are_rejected(
    bad_name: str,
    tmp_path: Path,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        UserPreset.from_factory(0, bad_name)
    with pytest.raises((TypeError, ValueError)):
        load_user_preset(bad_name, directory=tmp_path)
    assert not any(tmp_path.iterdir())


def test_invalid_schema_version_and_patch_are_rejected(tmp_path: Path) -> None:
    saved_path = save_user_preset(_edited_preset(), directory=tmp_path)
    document = json.loads(saved_path.read_text(encoding="utf-8"))

    document["schema_version"] = USER_PRESET_SCHEMA_VERSION + 1
    saved_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(UnsupportedUserPresetVersionError, match="schema version"):
        load_user_preset("My Wide Pad", directory=tmp_path)

    document["schema_version"] = USER_PRESET_SCHEMA_VERSION
    document["patch"]["filter_cutoff_hz"] = 20_001.0
    saved_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(InvalidUserPresetError, match="filter_cutoff_hz"):
        load_user_preset("My Wide Pad", directory=tmp_path)

    document["patch"].pop("waveform_a")
    saved_path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(InvalidUserPresetError, match="missing patch fields"):
        load_user_preset("My Wide Pad", directory=tmp_path)


def test_save_refuses_overwrite_until_explicitly_enabled(tmp_path: Path) -> None:
    original = _edited_preset()
    replacement = UserPreset.from_factory(
        72,
        "My Wide Pad",
        master_gain=0.22,
        brightness=0.33,
        reverb_mix=0.1,
    )
    target = save_user_preset(original, directory=tmp_path)

    with pytest.raises(FileExistsError, match="already exists"):
        save_user_preset(replacement, directory=tmp_path)
    assert load_user_preset("My Wide Pad", directory=tmp_path) == original

    replaced_path = save_user_preset(replacement, directory=tmp_path, overwrite=True)
    assert replaced_path == target
    assert load_user_preset("My Wide Pad", directory=tmp_path) == replacement
    assert not tuple(tmp_path.glob("*.tmp"))


def test_list_is_deterministic_and_delete_has_explicit_missing_behavior(
    tmp_path: Path,
) -> None:
    for name in ("zebra pad", "Alpha Lead", "middle keys"):
        save_user_preset(UserPreset.from_factory(0, name), directory=tmp_path)

    assert tuple(preset.custom_name for preset in list_user_presets(directory=tmp_path)) == (
        "Alpha Lead",
        "middle keys",
        "zebra pad",
    )
    assert delete_user_preset("MIDDLE KEYS", directory=tmp_path) is True
    assert tuple(preset.custom_name for preset in list_user_presets(directory=tmp_path)) == (
        "Alpha Lead",
        "zebra pad",
    )
    with pytest.raises(FileNotFoundError):
        delete_user_preset("middle keys", directory=tmp_path)
    assert delete_user_preset("middle keys", directory=tmp_path, missing_ok=True) is False


def test_default_directory_uses_local_app_data_then_home_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    assert default_preset_directory() == local_app_data / "SammyBlaze" / "presets"

    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "Home"))
    assert default_preset_directory() == tmp_path / "Home" / ".sammyblaze" / "presets"


def test_source_program_identity_cannot_be_forged_in_a_document(tmp_path: Path) -> None:
    saved_path = save_user_preset(_edited_preset(), directory=tmp_path)
    document = json.loads(saved_path.read_text(encoding="utf-8"))
    document["source_factory_program_id"] = get_preset(73).program_id
    saved_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(InvalidUserPresetError, match="program_id must match"):
        load_user_preset("My Wide Pad", directory=tmp_path)
