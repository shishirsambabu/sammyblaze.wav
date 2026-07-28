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
