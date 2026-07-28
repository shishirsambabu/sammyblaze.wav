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
    """Map right-hand position to musical expression and effect-send controls.

    The default CC layout is intentionally conventional so the performer can use
    the instrument with a synth, DAW, or hardware module without a custom plug-in:
    CC7 volume, CC11 expression, CC10 pan, CC91 reverb, CC94 delay, and CC93 chorus.
    """

    smoothing: float = 0.2
    expression_cc: int = 11
    pan_cc: int = 10
    volume_cc: int = 7
    reverb_cc: int = 91
    delay_cc: int = 94
    chorus_cc: int = 93
    neutral_center_x: float = 0.5
    neutral_center_y: float = 0.5
    neutral_depth: float = 0.0
    sensitivity: float = 1.0
    _expression: SmoothedControl = field(init=False)
    _pan: SmoothedControl = field(init=False)
    _volume: SmoothedControl = field(init=False)
    _reverb: SmoothedControl = field(init=False)
    _delay: SmoothedControl = field(init=False)
    _chorus: SmoothedControl = field(init=False)

    def __post_init__(self) -> None:
        self._expression = SmoothedControl(self.smoothing)
        self._pan = SmoothedControl(self.smoothing)
        self._volume = SmoothedControl(self.smoothing)
        self._reverb = SmoothedControl(self.smoothing)
        self._delay = SmoothedControl(self.smoothing)
        self._chorus = SmoothedControl(self.smoothing)
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

    def effect_controls(self, features: GestureFeatures) -> tuple[tuple[int, int], ...]:
        """Return volume and send-level controls driven by the right hand.

        Pinching increases reverb, moving toward the camera increases delay, and
        moving away from the neutral horizontal point increases chorus. These
        mappings are deliberately continuous and bounded for predictable live use.
        """

        if features.handedness != "right":
            return ()
        volume_input = 0.5 + (self.neutral_center_y - features.center_y) * self.sensitivity
        reverb_input = 1.0 - features.pinch_distance / 0.9
        delay_input = 0.5 + (self.neutral_depth - features.depth) * self.sensitivity
        chorus_input = abs(features.center_x - self.neutral_center_x) * 2.0 * self.sensitivity
        return (
            (self.volume_cc, self._volume.update(volume_input)),
            (self.reverb_cc, self._reverb.update(reverb_input)),
            (self.delay_cc, self._delay.update(delay_input)),
            (self.chorus_cc, self._chorus.update(chorus_input)),
        )
