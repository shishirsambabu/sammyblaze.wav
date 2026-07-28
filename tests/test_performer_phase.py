from handmusic.app import default_runtime
from handmusic.common.events import GestureKind
from handmusic.common.models import GestureFeatures
from handmusic.gestures.state_machine import GestureConfig, GestureStateMachine
from handmusic.music.midi_output import MemoryMidiOutput
from handmusic.music.performance import LeadScaleMode
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


def test_gesture_language_adds_chord_pose_and_designated_scale_mode_command() -> None:
    machine = GestureStateMachine(GestureConfig(cooldown_ms=0))
    chord_pose = feature("left", 0, fingers=(True, True, False, False, False))
    assert machine.process(chord_pose) == []
    chord_event = machine.process(
        feature("left", 180, fingers=(True, True, False, False, False))
    )[0]
    assert (chord_event.kind, chord_event.value) == (GestureKind.SELECT_CHORD, 1)

    pinch = feature("left", 300, fingers=(False, True, True, True, False), pinch=0.2)
    assert machine.process(pinch) == []
    assert (
        machine.process(
            feature("left", 700, fingers=(False, True, True, True, False), pinch=0.2)
        )[0].kind
        is GestureKind.CYCLE_SCALE_MODE
    )


def test_two_hand_runtime_plays_chord_scale_and_sustain() -> None:
    output = MemoryMidiOutput()
    runtime, _ = default_runtime(output)
    runtime.gestures.config = GestureConfig(cooldown_ms=0)

    runtime.handle_features(feature("left", 0, fingers=(True, False, False, False, False)))
    runtime.handle_features(feature("left", 180, fingers=(True, False, False, False, False)))
    assert runtime.armed is True
    assert output.messages[:4] == [
        ("note_on", 48, 92),
        ("note_on", 52, 92),
        ("note_on", 55, 92),
        ("note_on", 59, 92),
    ]

    runtime.handle_features(feature("right", 200, x=0.2, y=0.5))
    assert ("note_on", 65, 77) in output.messages
    runtime.handle_features(feature("right", 220, x=1.0, y=0.5))
    assert ("note_on", 84, 77) in output.messages

    runtime.notes.set_sustain(True)
    assert runtime.notes.sustain_enabled is True
    assert ("cc", 64, 127) in output.messages

    runtime.handle_features(feature("left", 900, fingers=(False,) * 5))
    runtime.handle_features(feature("left", 1020, fingers=(False,) * 5))
    assert runtime.armed is False
    runtime.close()


def test_left_pinch_cycles_chord_relative_scale_mode() -> None:
    output = MemoryMidiOutput()
    runtime, _ = default_runtime(output)
    runtime.gestures.config = GestureConfig(cooldown_ms=0)
    runtime.handle_features(feature("left", 0, fingers=(True, False, False, False, False)))
    runtime.handle_features(feature("left", 180, fingers=(True, False, False, False, False)))
    runtime.handle_features(
        feature("left", 300, fingers=(False, True, True, True, False), pinch=0.2)
    )
    runtime.handle_features(
        feature("left", 700, fingers=(False, True, True, True, False), pinch=0.2)
    )
    assert runtime.scale.mode is LeadScaleMode.COLOR
    assert runtime.scale.label == "C Lydian"
    runtime.close()


def test_right_hand_effect_mapper_emits_standard_send_controls() -> None:
    output = MemoryMidiOutput()
    runtime, _ = default_runtime(output)
    runtime.handle_features(feature("right", 0, x=0.25, y=0.25, depth=-0.5, pinch=0.0))
    assert ("cc", 7, 102) in output.messages
    assert ("cc", 91, 127) in output.messages
    assert ("cc", 94, 64) in output.messages
    assert ("cc", 93, 8) in output.messages
