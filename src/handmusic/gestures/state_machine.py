from __future__ import annotations

from dataclasses import dataclass

from handmusic.common.events import GestureEvent, GestureKind
from handmusic.common.models import GestureFeatures


@dataclass(frozen=True, slots=True)
class GestureConfig:
    confidence: float = 0.7
    open_palm_hold_ms: int = 500
    fist_hold_ms: int = 120
    pinch_hold_ms: int = 180
    swipe_velocity_threshold: float = 0.35
    cooldown_ms: int = 500
    neutral_pinch_distance: float = 0.9


class GestureStateMachine:
    """Turn noisy feature frames into one-shot, performer-safe events."""

    def __init__(self, config: GestureConfig | None = None) -> None:
        self.config = config or GestureConfig()
        self._candidate: dict[str, tuple[str, int]] = {}
        self._emitted: set[tuple[str, str]] = set()
        self._cooldown_until: dict[str, int] = {}

    def _stable(self, hand: str, label: str, timestamp_ms: int, hold_ms: int) -> bool:
        existing = self._candidate.get(hand)
        if existing is None or existing[0] != label:
            self._candidate[hand] = (label, timestamp_ms)
            return hold_ms == 0
        return timestamp_ms - existing[1] >= hold_ms

    def _event(self, kind: GestureKind, features: GestureFeatures) -> GestureEvent:
        return GestureEvent(kind, features.handedness, features.confidence, features.timestamp_ms)

    def process(self, features: GestureFeatures) -> list[GestureEvent]:
        if features.confidence < self.config.confidence:
            return []
        hand = features.handedness
        if hand == "unknown":
            hand = "unknown"
        now = features.timestamp_ms
        events: list[GestureEvent] = []
        open_palm = sum(features.fingers_open) >= 4
        fist = sum(features.fingers_open) == 0
        pinch = features.pinch_distance <= 0.45
        neutral = not open_palm and not fist and not pinch

        # Re-arm only after the pose has been released. Fist is an emergency
        # command and must remain available even during another gesture's cooldown.
        if neutral:
            self._emitted = {item for item in self._emitted if item[0] != hand}

        def emit_once(label: str, kind: GestureKind, hold_ms: int) -> None:
            key = (hand, label)
            emergency = kind is GestureKind.STOP_ALL
            if (not emergency and now < self._cooldown_until.get(hand, 0)) or key in self._emitted:
                return
            if self._stable(hand, label, now, hold_ms):
                self._emitted.add(key)
                self._cooldown_until[hand] = now + self.config.cooldown_ms
                events.append(self._event(kind, features))

        # Motion commands take precedence over an open-palm pose. A performer
        # naturally swipes with an open hand, so static-pose detection must not
        # swallow the movement event.
        if (
            not fist
            and not pinch
            and abs(features.velocity_x) >= self.config.swipe_velocity_threshold
        ):
            self._candidate.pop(hand, None)
            emit_once(
                "swipe_right" if features.velocity_x > 0 else "swipe_left",
                GestureKind.NEXT_CHORD if features.velocity_x > 0 else GestureKind.PREVIOUS_CHORD,
                0,
            )
            return events

        if open_palm:
            emit_once("open_palm", GestureKind.ARM, self.config.open_palm_hold_ms)
        elif fist:
            emit_once("fist", GestureKind.STOP_ALL, self.config.fist_hold_ms)
        elif pinch:
            emit_once("pinch", GestureKind.TOGGLE_ARPEGGIATOR, self.config.pinch_hold_ms)
        else:
            self._candidate.pop(hand, None)
            if features.velocity_x >= self.config.swipe_velocity_threshold:
                emit_once("swipe_right", GestureKind.NEXT_CHORD, 0)
            elif features.velocity_x <= -self.config.swipe_velocity_threshold:
                emit_once("swipe_left", GestureKind.PREVIOUS_CHORD, 0)
        return events
