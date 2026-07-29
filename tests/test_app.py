from handmusic.app import default_runtime
from handmusic.common.models import GestureFeatures


def test_runtime_closes_notes_on_stop_gesture() -> None:
    runtime, output = default_runtime()
    runtime.handle_features(
        GestureFeatures("left", (True,) * 5, 0.8, 0, 0.5, 0.5, 0, 0, 0, 0.95, 0)
    )
    runtime.handle_features(
        GestureFeatures("left", (True,) * 5, 0.8, 0, 0.5, 0.5, 0, 0, 0, 0.95, 500)
    )
    assert runtime.armed is True
    runtime.handle_features(
        GestureFeatures("left", (False,) * 5, 1.0, 1, 0.5, 0.5, 0, 0, 0, 0.95, 600)
    )
    runtime.handle_features(
        GestureFeatures("left", (False,) * 5, 1.0, 1, 0.5, 0.5, 0, 0, 0, 0.95, 720)
    )
    assert runtime.armed is False
    assert runtime.notes.active_notes == set()
    assert any(message[0] == "note_off" for message in output.messages)


def test_runtime_swipe_changes_chord_and_retriggers_notes() -> None:
    runtime, output = default_runtime()
    runtime.handle_features(
        GestureFeatures("left", (True,) * 5, 0.8, 0, 0.5, 0.5, 0, 0, 0, 0.95, 0)
    )
    runtime.handle_features(
        GestureFeatures("left", (True,) * 5, 0.8, 0, 0.5, 0.5, 0, 0, 0, 0.95, 500)
    )
    runtime.handle_features(
        GestureFeatures("left", (False,) * 5, 1.0, 1, 0.5, 0.5, 0, 0, 0, 0.95, 600)
    )
    runtime.handle_features(
        GestureFeatures("left", (True,) * 5, 1.0, 1, 0.5, 0.5, 0, 0.5, 0, 0.95, 1100)
    )
    assert runtime.chord_label == "A minor"
    assert output.messages[-3:] == [
        ("note_on", 57, 92),
        ("note_on", 60, 92),
        ("note_on", 64, 92),
    ]


def test_runtime_emits_right_hand_expression_controls() -> None:
    runtime, output = default_runtime()
    runtime.handle_features(
        GestureFeatures("right", (False,) * 5, 1.0, 0, 0.25, 0.25, 0, 0, 0, 0.95, 0)
    )
    assert ("cc", 11, 94) in output.messages
    assert ("cc", 1, 0) in output.messages
    assert ("cc", 74, 64) in output.messages


def test_runtime_selects_factory_sound_and_reports_it() -> None:
    runtime, output = default_runtime()

    runtime.select_sound(83)

    assert runtime.sound_program == 83
    assert ("program", 83, None) in output.messages
    assert "Sound: Infinite Bloom Pad" in runtime.status_label
