from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import hypot

from handmusic.common.models import GestureFeatures


def _safe_level(normalized: float, floor: float = 0.2) -> float:
    """Keep live hand control expressive without allowing an accidental hard mute."""

    normalized = max(0.0, min(1.0, normalized))
    return floor + (1.0 - floor) * normalized


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


@dataclass(frozen=True, slots=True)
class ExpressionState:
    """One performer-frame of spatial and musical expression."""

    x: float = 0.5
    y: float = 0.5
    z: float = 0.5
    motion: float = 0.0
    vibrato: int = 0
    expression: int = 64
    brightness: int = 64
    volume: int = 96
    reverb: int = 0
    delay: int = 0
    chorus: int = 0

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExpressionFrame:
    controls: tuple[tuple[int, int], ...]
    state: ExpressionState


@dataclass(slots=True)
class ExpressionController:
    """Map three-dimensional right-hand movement to expressive MIDI controls.

    The default CC layout is intentionally conventional so the performer can use
    the instrument with a synth, DAW, or hardware module without a custom plug-in:
    CC1 vibrato, CC7 volume, CC11 expression, CC74 brightness, CC91 reverb,
    CC94 delay, and CC93 chorus.
    """

    smoothing: float = 0.2
    expression_cc: int = 11
    vibrato_cc: int = 1
    brightness_cc: int = 74
    volume_cc: int = 7
    reverb_cc: int = 91
    delay_cc: int = 94
    chorus_cc: int = 93
    neutral_center_x: float = 0.5
    neutral_center_y: float = 0.5
    neutral_depth: float = 0.0
    sensitivity: float = 1.0
    _expression: SmoothedControl = field(init=False)
    _vibrato: SmoothedControl = field(init=False)
    _brightness: SmoothedControl = field(init=False)
    _volume: SmoothedControl = field(init=False)
    _reverb: SmoothedControl = field(init=False)
    _delay: SmoothedControl = field(init=False)
    _chorus: SmoothedControl = field(init=False)
    _last_state: ExpressionState = field(default_factory=ExpressionState, init=False)

    def __post_init__(self) -> None:
        self._expression = SmoothedControl(self.smoothing)
        self._vibrato = SmoothedControl(min(1.0, self.smoothing * 1.5))
        self._brightness = SmoothedControl(self.smoothing)
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

    @property
    def last_state(self) -> ExpressionState:
        return self._last_state

    def process(self, features: GestureFeatures) -> ExpressionFrame:
        if features.handedness != "right":
            return ExpressionFrame((), self._last_state)

        vertical = (self.neutral_center_y - features.center_y) * self.sensitivity
        toward = (self.neutral_depth - features.depth) * self.sensitivity
        motion = max(0.0, min(1.0, (hypot(features.velocity_x, features.velocity_y) - 0.08) / 1.2))
        expression_input = 0.5 + vertical * 0.7 + toward * 0.6
        depth_input = 0.5 + toward
        volume_input = 0.5 + vertical
        reverb_input = 1.0 - features.pinch_distance / 0.9
        delay_input = max(0.0, toward)
        chorus_input = motion * 0.75 + abs(vertical) * 0.25

        expression = self._expression.update(_safe_level(expression_input))
        vibrato = self._vibrato.update(motion)
        brightness = self._brightness.update(depth_input)
        volume = self._volume.update(_safe_level(volume_input))
        reverb = self._reverb.update(reverb_input)
        delay = self._delay.update(delay_input)
        chorus = self._chorus.update(chorus_input)
        z = max(0.0, min(1.0, depth_input))
        self._last_state = ExpressionState(
            x=max(0.0, min(1.0, features.center_x)),
            y=max(0.0, min(1.0, features.center_y)),
            z=z,
            motion=motion,
            vibrato=vibrato,
            expression=expression,
            brightness=brightness,
            volume=volume,
            reverb=reverb,
            delay=delay,
            chorus=chorus,
        )
        return ExpressionFrame(
            (
                (self.expression_cc, expression),
                (self.vibrato_cc, vibrato),
                (self.brightness_cc, brightness),
                (self.volume_cc, volume),
                (self.reverb_cc, reverb),
                (self.delay_cc, delay),
                (self.chorus_cc, chorus),
            ),
            self._last_state,
        )

    def controls(self, features: GestureFeatures) -> tuple[tuple[int, int], ...]:
        frame = self.process(features)
        return frame.controls[:3]

    def effect_controls(self, features: GestureFeatures) -> tuple[tuple[int, int], ...]:
        frame = self.process(features)
        return frame.controls[3:]
