from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from handmusic.music.user_presets import load_user_preset
from handmusic.ui.desktop import PerformerWindow


@pytest.fixture(scope="module")
def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_cockpit_constructs_with_live_sound_lab(
    application: QApplication,
    tmp_path,
) -> None:
    window = PerformerWindow(
        camera_index=2,
        output_mode="plugin",
        sound_program=24,
        preset_directory=tmp_path,
    )
    application.processEvents()

    assert window.camera.value() == 2
    assert window.output.currentData() == "plugin"
    assert len(window._parameter_knobs) == 18
    assert window.pages.count() == 4
    assert window.sound.count() == 12
    assert window._current_patch.program_id == 24

    window.close()


def test_sound_lab_edits_and_saves_complete_user_preset(
    application: QApplication,
    tmp_path,
) -> None:
    window = PerformerWindow(sound_program=0, preset_directory=tmp_path)
    window._show_page(1)
    window._parameter_knobs["reverb_mix"].set_value(64)
    window._parameter_knobs["master_gain"].set_value(82)
    application.processEvents()

    assert window._current_patch.reverb_mix == pytest.approx(0.64)
    assert window._master_gain == pytest.approx(0.82)

    window.save_current_preset("Stage Atmosphere")
    saved = load_user_preset("Stage Atmosphere", directory=tmp_path)
    assert saved.reverb_mix == pytest.approx(0.64)
    assert saved.master_gain == pytest.approx(0.82)
    assert window.user_presets.findData("Stage Atmosphere") > 0

    window.close()
