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
    neutral_center_x: float = 0.5
    neutral_center_y: float = 0.5
    sensitivity: float = 1.0
    _expression: SmoothedControl = field(init=False)
    _pan: SmoothedControl = field(init=False)

    def __post_init__(self) -> None:
        self._expression = SmoothedControl(self.smoothing)
        self._pan = SmoothedControl(self.smoothing)
        if not 0.0 <= self.neutral_center_x <= 1.0:
            raise ValueError("neutral_center_x must be between 0 and 1")
        if not 0.0 <= self.neutral_center_y <= 1.0:
            raise ValueError("neutral_center_y must be between 0 and 1")
        if self.sensitivity <= 0.0:
            raise ValueError("sensitivity must be positive")

    def controls(self, features: GestureFeatures) -> tuple[tuple[int, int], ...]:
        if features.handedness != "right":
            return ()
        expression_input = 0.5 + (self.neutral_center_y - features.center_y) * self.sensitivity
        pan_input = 0.5 + (features.center_x - self.neutral_center_x) * self.sensitivity
        expression = self._expression.update(expression_input)
        pan = self._pan.update(pan_input)
        return ((self.expression_cc, expression), (self.pan_cc, pan))
