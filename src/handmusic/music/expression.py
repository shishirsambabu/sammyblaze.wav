from __future__ import annotations

from dataclasses import dataclass, field

from handmusic.common.models import GestureFeatures


@dataclass(slots=True)
class SmoothedControl:
    """Exponential smoother that returns bounded MIDI values."""

    alpha: float = 0.2
    _value: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not 0.0 < self.alpha <= 1.0:
            raise ValueError("alpha must be greater than 0 and no more than 1")

    def update(self, normalized: float) -> int:
        normalized = max(0.0, min(1.0, normalized))
        if self._value is None:
            self._value = normalized
        else:
            self._value = self.alpha * normalized + (1.0 - self.alpha) * self._value
        return round(self._value * 127)


@dataclass(slots=True)
class ExpressionController:
    """Map right-hand position to smoothed expression and pan controls."""

    smoothing: float = 0.2
    expression_cc: int = 11
    pan_cc: int = 10
    _expression: SmoothedControl = field(init=False)
    _pan: SmoothedControl = field(init=False)

    def __post_init__(self) -> None:
        self._expression = SmoothedControl(self.smoothing)
        self._pan = SmoothedControl(self.smoothing)

    def controls(self, features: GestureFeatures) -> tuple[tuple[int, int], ...]:
        if features.handedness != "right":
            return ()
        expression = self._expression.update(1.0 - features.center_y)
        pan = self._pan.update(features.center_x)
        return ((self.expression_cc, expression), (self.pan_cc, pan))
