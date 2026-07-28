from handmusic.app import default_runtime
from handmusic.common.events import GestureKind
from handmusic.common.models import GestureFeatures
from handmusic.gestures.state_machine import GestureConfig, GestureStateMachine
from handmusic.music.midi_output import MemoryMidiOutput
from handmusic.music.modes import PerformanceMode
from handmusic.music.progression import progression_for, progression_names
from handmusic.music.scale import ScaleEngine, scale_for


def feature(
    hand: str,
    timestamp: int,
    *,
    fingers: tuple[bool, bool, bool, bool, bool] = (False,) * 5,
    pinch: float = 1.0,
    x: float = 0.5,
    y: float = 0.5,
    depth: float = 0.0,
    velocity_x: float = 0.0,
) -> GestureFeatures:
    return GestureFeatures(
        hand,
        fingers,
        pinch,
        0.0,
        x,
        y,
        depth,
        velocity_x,
        0.0,
        1.0,
        timestamp,
    )


def test_progression_catalog_contains_multiple_playable_sequences() -> None:
    assert len(progression_names()) >= 6
    assert progression_for("jazz_ii_v_i").current_notes == (62, 65, 69, 72)


def test_scale_engine_maps_right_hand_width_to_notes() -> None:
    engine = ScaleEngine(scale_for("minor_pentatonic"), root_midi=60, octaves=1)
    assert engine.note_for_position(0.0) == 60
    assert engine.note_for_position(1.0) == 72


def test_gesture_language_adds_mode_and_sustain_commands() -> None:
    machine = GestureStateMachine(GestureConfig(cooldown_ms=0))
    pinch = feature("left", 0, fingers=(False, True, False, False, False), pinch=0.2)
    assert machine.process(pinch) == []
    assert (
        machine.process(
            feature("left", 180, fingers=(False, True, False, False, False), pinch=0.2)
        )[0].kind
        is GestureKind.CYCLE_MODE
    )
    machine.process(feature("left", 200))
    thumb_only = feature("left", 300, fingers=(True, False, False, False, False))
    assert machine.process(thumb_only) == []
    assert (
        machine.process(
            feature("left", 520, fingers=(True, False, False, False, False))
        )[0].kind
        is GestureKind.TOGGLE_SUSTAIN
    )


def test_two_hand_runtime_plays_chord_scale_and_sustain() -> None:
    output = MemoryMidiOutput()
    runtime, _ = default_runtime(output)
    runtime.gestures.config = GestureConfig(cooldown_ms=0)

    runtime.handle_features(feature("left", 0, fingers=(True,) * 5))
    runtime.handle_features(feature("left", 500, fingers=(True,) * 5))
    assert runtime.armed is True
    assert output.messages[:3] == [
        ("note_on", 48, 92),
        ("note_on", 52, 92),
        ("note_on", 55, 92),
    ]

    runtime.handle_features(feature("right", 520, x=0.2, y=0.5))
    assert ("note_on", 65, 77) in output.messages
    runtime.handle_features(feature("right", 540, x=1.0, y=0.5))
    assert ("note_on", 84, 77) in output.messages

    runtime.handle_features(
        feature("left", 600, fingers=(True, False, False, False, False))
    )
    runtime.handle_features(
        feature("left", 820, fingers=(True, False, False, False, False))
    )
    assert runtime.notes.sustain_enabled is True
    assert ("cc", 64, 127) in output.messages

    runtime.handle_features(feature("left", 900, fingers=(False,) * 5))
    runtime.handle_features(feature("left", 1020, fingers=(False,) * 5))
    assert runtime.mode is PerformanceMode.CHORD_SCALE
    runtime.close()


def test_left_pinch_cycles_runtime_mode_and_releases_disabled_voice() -> None:
    output = MemoryMidiOutput()
    runtime, _ = default_runtime(output)
    runtime.gestures.config = GestureConfig(cooldown_ms=0)
    runtime.handle_features(feature("left", 0, fingers=(True,) * 5))
    runtime.handle_features(feature("left", 500, fingers=(True,) * 5))
    runtime.handle_features(
        feature("left", 600, fingers=(False, True, False, False, False), pinch=0.2)
    )
    runtime.handle_features(
        feature("left", 780, fingers=(False, True, False, False, False), pinch=0.2)
    )
    assert runtime.mode is PerformanceMode.CHORD_ONLY
    runtime.handle_features(feature("right", 800, x=0.2))
    assert runtime.last_scale_note is None
    assert runtime.notes.active_notes == {48, 52, 55}
    runtime.close()


def test_right_hand_effect_mapper_emits_standard_send_controls() -> None:
    output = MemoryMidiOutput()
    runtime, _ = default_runtime(output)
    runtime.handle_features(feature("right", 0, x=0.25, y=0.25, depth=-0.5, pinch=0.0))
    assert ("cc", 7, 102) in output.messages
    assert ("cc", 91, 127) in output.messages
    assert ("cc", 94, 127) in output.messages
    assert ("cc", 93, 64) in output.messages
