from handmusic.common.events import GestureKind
from handmusic.common.models import GestureFeatures
from handmusic.gestures.state_machine import GestureConfig, GestureStateMachine


def features(timestamp: int, *, fingers=(True, True, True, True, True), pinch=1.0, vx=0.0):
    return GestureFeatures("left", fingers, pinch, 0.0, 0.5, 0.5, 0.0, vx, 0.0, 0.95, timestamp)


def test_open_palm_requires_hold_and_emits_once_until_neutral() -> None:
    machine = GestureStateMachine(GestureConfig(open_palm_hold_ms=500, cooldown_ms=0))
    assert machine.process(features(0)) == []
    assert machine.process(features(499)) == []
    assert [event.kind for event in machine.process(features(500))] == [GestureKind.ARM]
    assert machine.process(features(700)) == []
    machine.process(features(800, fingers=(True, False, False, False, False)))
    assert machine.process(features(900)) == []


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
