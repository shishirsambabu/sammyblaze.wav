from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

import handmusic.ui.desktop as desktop_module
from handmusic.app import default_runtime
from handmusic.music.presets import get_preset
from handmusic.music.user_presets import load_user_preset
from handmusic.tracking.camera import CameraHealthSnapshot
from handmusic.ui.desktop import PerformerWindow, SessionWorker


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


def test_performance_state_updates_arm_and_sustain_controls(
    application: QApplication,
    tmp_path,
) -> None:
    window = PerformerWindow(preset_directory=tmp_path)

    window._set_performance_state(
        "ARMED | Mode: chord + scale | Chord latch: active | Pedal: on"
    )
    application.processEvents()

    assert window.arm_badge.text() == "ARMED"
    assert window.pedal_button.isChecked() is True

    window._set_performance_state(
        "DISARMED | Mode: chord + scale | Chord latch: ready | Pedal: off"
    )
    application.processEvents()

    assert window.arm_badge.text() == "DISARMED"
    assert window.pedal_button.isChecked() is False
    window.close()


def test_worker_reports_running_only_after_first_camera_frame(
    application: QApplication,
) -> None:
    worker = SessionWorker(camera_index=0, output_mode="null", midi_port=None)
    states: list[str] = []
    frames: list[object] = []
    worker.state_changed.connect(states.append)
    worker.frame_ready.connect(frames.append)
    frame = object()

    worker._publish_frame(frame)
    worker._publish_frame(frame)
    application.processEvents()

    assert states == ["Running"]
    assert frames == [frame, frame]


def test_audio_callback_failure_is_visible_on_perform_page(
    application: QApplication,
    tmp_path,
) -> None:
    window = PerformerWindow(preset_directory=tmp_path)

    window._set_audio_health("Audio callback status: output underflow")
    application.processEvents()

    assert window.metric_audio.value_text == "AUDIO XRUN"
    assert window.metric_audio.toolTip() == "Audio callback status: output underflow"
    assert "underflow" in window.status.text()
    window.close()


def test_audio_backend_is_visible_on_perform_page(
    application: QApplication,
    tmp_path,
) -> None:
    window = PerformerWindow(preset_directory=tmp_path)

    window._set_audio_health("Native C++ audio core ready")
    application.processEvents()
    assert window.metric_audio.value_text == "NATIVE CORE"

    window._set_audio_health(
        "Native unison quality budget active: requested 16, rendering 4 lanes/voice"
    )
    application.processEvents()
    assert window.metric_audio.value_text == "UNISON ECO"
    assert "rendering 4 lanes/voice" in window.metric_audio.toolTip()

    window._set_audio_health("Native unison full quality: 16 lanes/voice")
    application.processEvents()
    assert window.metric_audio.value_text == "NATIVE CORE"

    window._set_audio_health(
        "Native C++ audio core unavailable; Python compatibility synth is active"
    )
    application.processEvents()
    assert window.metric_audio.value_text == "PYTHON FALLBACK"
    window.close()


def test_camera_recovery_is_visible_on_perform_page(
    application: QApplication,
    tmp_path,
) -> None:
    window = PerformerWindow(preset_directory=tmp_path)

    window._set_camera_health("Camera: recovering...")
    application.processEvents()
    assert window.camera_badge.text() == "CAMERA RECOVERING"

    window._set_camera_health("Camera: recovered (recovery 1) via DirectShow")
    application.processEvents()
    assert window.camera_badge.text() == "CAMERA ON"

    window._set_camera_health("Camera recovery failed")
    application.processEvents()
    assert window.camera_badge.text() == "CAMERA ERROR"

    worker = SessionWorker(camera_index=0, output_mode="null", midi_port=None)
    messages: list[str] = []
    worker.camera_health.connect(messages.append)
    worker._publish_camera_health(
        CameraHealthSnapshot(
            camera_index=0,
            state="recovered",
            generation=2,
            backend="DirectShow",
        )
    )
    application.processEvents()
    assert messages == ["Camera: recovered (recovery 2) via DirectShow"]
    window.close()


def test_worker_marshals_live_controls_onto_runtime_thread(
    application: QApplication,
) -> None:
    worker = SessionWorker(camera_index=0, output_mode="null", midi_port=None)
    runtime, output = default_runtime()
    worker.runtime = runtime
    worker.output_target = output

    worker.toggle_sustain()

    assert runtime.notes.sustain_enabled is False
    worker._drain_runtime_commands()
    application.processEvents()
    assert runtime.notes.sustain_enabled is True

    worker.select_sound(83)
    worker.apply_sound_patch(get_preset(83), master_gain=0.6, brightness=0.7)
    assert runtime.sound_program == 0
    worker._drain_runtime_commands()
    assert runtime.sound_program == 83
    assert ("program", 83, None) in output.messages


def test_worker_treats_camera_open_cancellation_as_clean_stop(
    application: QApplication,
    monkeypatch,
) -> None:
    worker = SessionWorker(camera_index=0, output_mode="null", midi_port=None)
    failures: list[str] = []
    states: list[str] = []
    worker.failed.connect(failures.append)
    worker.state_changed.connect(states.append)

    def cancelled_run_camera(*_args, **_kwargs) -> None:
        worker.stop_event.set()
        raise RuntimeError("Camera 0 open cancelled")

    monkeypatch.setattr(desktop_module, "run_camera", cancelled_run_camera)

    worker.run()
    application.processEvents()

    assert failures == []
    assert states[-1] == "Stopped"
