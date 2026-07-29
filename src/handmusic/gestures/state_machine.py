from __future__ import annotations

from dataclasses import dataclass

from handmusic.common.events import GestureEvent, GestureKind
from handmusic.common.models import GestureFeatures

FingerPose = tuple[bool, bool, bool, bool, bool]

# Finger order is index, middle, ring, pinky, thumb. Fist and pinch are
# deliberately reserved for panic and scale-mode commands.
CHORD_POSES: dict[FingerPose, int] = {
    (True, False, False, False, False): 0,  # index: I
    (True, True, False, False, False): 1,  # index + middle: ii
    (True, True, True, False, False): 2,  # three fingers: iii
    (True, True, True, True, False): 3,  # four fingers: IV
    (True, True, True, True, True): 4,  # open palm: V
    (False, False, False, True, True): 5,  # shaka: vi
    (True, False, False, False, True): 6,  # wide L: vii
}


@dataclass(frozen=True, slots=True)
class GestureConfig:
    confidence: float = 0.7
    open_palm_hold_ms: int = 500
    fist_hold_ms: int = 120
    pinch_hold_ms: int = 180
    sustain_hold_ms: int = 220
    mode_hold_ms: int = 180
    chord_pose_hold_ms: int = 180
    scale_mode_hold_ms: int = 400
    chord_pose_velocity_max: float = 0.25
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
        self._active_chord_pose: dict[str, int] = {}

    def _stable(self, hand: str, label: str, timestamp_ms: int, hold_ms: int) -> bool:
        existing = self._candidate.get(hand)
        if existing is None or existing[0] != label:
            self._candidate[hand] = (label, timestamp_ms)
            return hold_ms == 0
        return timestamp_ms - existing[1] >= hold_ms

    def _event(
        self,
        kind: GestureKind,
        features: GestureFeatures,
        value: int | str | None = None,
    ) -> GestureEvent:
        return GestureEvent(
            kind,
            features.handedness,
            features.confidence,
            features.timestamp_ms,
            value,
        )

    def process(self, features: GestureFeatures) -> list[GestureEvent]:
        if features.confidence < self.config.confidence:
            return []
        hand = features.handedness
        if hand == "unknown":
            hand = "unknown"
        now = features.timestamp_ms
        events: list[GestureEvent] = []
        fist = sum(features.fingers_open) == 0
        pinch = features.pinch_distance <= 0.45
        chord_index = CHORD_POSES.get(features.fingers_open)
        neutral = not fist and not pinch and chord_index is None

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

        if fist:
            self._active_chord_pose.pop(hand, None)
            emit_once("fist", GestureKind.STOP_ALL, self.config.fist_hold_ms)
        elif pinch:
            self._active_chord_pose.pop(hand, None)
            emit_once(
                "scale_mode",
                GestureKind.CYCLE_SCALE_MODE,
                self.config.scale_mode_hold_ms,
            )
        elif (
            chord_index is not None
            and abs(features.velocity_x) <= self.config.chord_pose_velocity_max
            and abs(features.velocity_y) <= self.config.chord_pose_velocity_max
        ):
            label = f"chord_pose_{chord_index}"
            if (
                self._active_chord_pose.get(hand) != chord_index
                and self._stable(hand, label, now, self.config.chord_pose_hold_ms)
            ):
                self._active_chord_pose[hand] = chord_index
                events.append(self._event(GestureKind.SELECT_CHORD, features, chord_index))
        else:
            self._candidate.pop(hand, None)
            if features.velocity_x >= self.config.swipe_velocity_threshold:
                emit_once("swipe_right", GestureKind.NEXT_CHORD, 0)
            elif features.velocity_x <= -self.config.swipe_velocity_threshold:
                emit_once("swipe_left", GestureKind.PREVIOUS_CHORD, 0)
        return events
