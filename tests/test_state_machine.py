from handmusic.common.events import GestureKind
from handmusic.common.models import GestureFeatures
from handmusic.gestures.state_machine import GestureConfig, GestureStateMachine


def features(timestamp: int, *, fingers=(True, True, True, True, True), pinch=1.0, vx=0.0):
    return GestureFeatures("left", fingers, pinch, 0.0, 0.5, 0.5, 0.0, vx, 0.0, 0.95, timestamp)


def test_open_palm_selects_fifth_chord_after_stable_hold() -> None:
    machine = GestureStateMachine(GestureConfig(chord_pose_hold_ms=180, cooldown_ms=0))
    assert machine.process(features(0)) == []
    assert machine.process(features(179)) == []
    event = machine.process(features(180))[0]
    assert event.kind is GestureKind.SELECT_CHORD
    assert event.value == 4
    assert machine.process(features(700)) == []


def test_every_canonical_pose_selects_its_harmonic_degree() -> None:
    poses = (
        (True, False, False, False, False),
        (True, True, False, False, False),
        (True, True, True, False, False),
        (True, True, True, True, False),
        (True, True, True, True, True),
        (False, False, False, True, True),
        (True, False, False, False, True),
    )
    for expected, pose in enumerate(poses):
        machine = GestureStateMachine(GestureConfig(chord_pose_hold_ms=180, cooldown_ms=0))
        assert machine.process(features(0, fingers=pose)) == []
        event = machine.process(features(180, fingers=pose))[0]
        assert (event.kind, event.value) == (GestureKind.SELECT_CHORD, expected)


def test_swipes_are_discrete_events() -> None:
    machine = GestureStateMachine(GestureConfig(cooldown_ms=0))
    assert [
        event.kind
        for event in machine.process(features(0, fingers=(True, False, True, True, True), vx=0.5))
    ] == [GestureKind.NEXT_CHORD]


def test_low_confidence_is_ignored() -> None:
    machine = GestureStateMachine()
    low = GestureFeatures("left", (False,) * 5, 0.1, 0, 0, 0, 0, 0, 0, 0.2, 0)
    assert machine.process(low) == []
