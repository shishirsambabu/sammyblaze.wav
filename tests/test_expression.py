import pytest

from handmusic.common.models import GestureFeatures
from handmusic.music.expression import ExpressionController, SmoothedControl


def hand_features(*, handedness: str, x: float, y: float) -> GestureFeatures:
    return GestureFeatures(handedness, (False,) * 5, 1.0, 0.0, x, y, 0.0, 0.0, 0.0, 1.0, 0)


def test_smoother_clamps_and_converges() -> None:
    smoother = SmoothedControl(alpha=0.5)
    assert smoother.update(2.0) == 127
    assert smoother.update(0.0) == 64


def test_only_right_hand_drives_expression_controls() -> None:
    controller = ExpressionController(smoothing=1.0)
    assert controller.controls(hand_features(handedness="left", x=0.2, y=0.2)) == ()
    assert controller.controls(hand_features(handedness="right", x=0.25, y=0.25)) == (
        (11, 95),
        (10, 32),
    )


@pytest.mark.parametrize("alpha", [0.0, -0.1, 1.1])
def test_smoother_rejects_invalid_alpha(alpha: float) -> None:
    with pytest.raises(ValueError):
        SmoothedControl(alpha)
