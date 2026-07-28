from pathlib import Path

import pytest

from handmusic.calibration import CalibrationSession, PerformerPreset, PresetStore
from handmusic.common.models import GestureFeatures


def feature(x: float, y: float, *, confidence: float = 1.0) -> GestureFeatures:
    return GestureFeatures("right", (False,) * 5, 1.0, 0.0, x, y, 0.4, 0.0, 0.0, confidence, 0)


def test_calibration_uses_median_and_rejects_low_confidence() -> None:
    session = CalibrationSession(min_confidence=0.8)
    assert session.add(feature(0.2, 0.3, confidence=0.5)) is False
    assert session.add(feature(0.4, 0.5)) is True
    assert session.add(feature(0.6, 0.7)) is True
    preset = session.finalize("performer")
    assert preset.neutral_center_x == 0.5
    assert preset.neutral_center_y == 0.6


def test_preset_store_round_trips_atomically(tmp_path: Path) -> None:
    path = tmp_path / "presets" / "default.json"
    original = PerformerPreset("default", 0.5, 0.55, 0.4, midi_port="Virtual MIDI")
    PresetStore.save(path, original)
    assert PresetStore.load(path) == original


def test_invalid_preset_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 2}', encoding="utf-8")
    with pytest.raises(ValueError):
        PresetStore.load(path)
