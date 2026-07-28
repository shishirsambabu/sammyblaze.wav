from __future__ import annotations

import json
import tempfile
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic


def _p95(values: deque[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))
    return ordered[index]


@dataclass(frozen=True, slots=True)
class TelemetrySnapshot:
    frames_seen: int
    hands_seen: int
    gestures_seen: int
    dropped_frames: int
    effective_fps: float
    mean_frame_interval_ms: float
    mean_frame_age_ms: float
    p95_frame_age_ms: float
    mean_gesture_latency_ms: float
    p95_gesture_latency_ms: float

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


class PerformanceTelemetry:
    """Bounded, hardware-independent metrics for one camera performance session."""

    def __init__(
        self,
        *,
        expected_fps: float = 30.0,
        max_samples: int = 180,
        clock_ms: Callable[[], float] | None = None,
    ) -> None:
        if expected_fps <= 0.0:
            raise ValueError("expected_fps must be positive")
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self.expected_fps = expected_fps
        self._expected_interval_ms = 1000.0 / expected_fps
        self._max_samples = max_samples
        self._clock_ms = clock_ms or (lambda: monotonic() * 1000.0)
        self._frame_intervals: deque[float] = deque(maxlen=max_samples)
        self._frame_ages: deque[float] = deque(maxlen=max_samples)
        self._gesture_latencies: deque[float] = deque(maxlen=max_samples)
        self._started_ms: float | None = None
        self._last_received_ms: float | None = None
        self._last_captured_ms: float | None = None
        self.frames_seen = 0
        self.hands_seen = 0
        self.gestures_seen = 0
        self.dropped_frames = 0

    def record_frame(self, captured_at_ms: int, received_at_ms: float | None = None) -> None:
        received = self._clock_ms() if received_at_ms is None else received_at_ms
        captured = float(captured_at_ms)
        if self._started_ms is None:
            self._started_ms = received
        if self._last_received_ms is not None:
            self._frame_intervals.append(max(0.0, received - self._last_received_ms))
        if self._last_captured_ms is not None:
            capture_gap = captured - self._last_captured_ms
            if capture_gap > self._expected_interval_ms * 1.5:
                expected_frames = round(capture_gap / self._expected_interval_ms)
                self.dropped_frames += max(0, expected_frames - 1)
        self._frame_ages.append(max(0.0, received - captured))
        self._last_received_ms = received
        self._last_captured_ms = captured
        self.frames_seen += 1

    def record_hand(self) -> None:
        self.hands_seen += 1

    def record_gesture(
        self,
        feature_timestamp_ms: int,
        processed_at_ms: float | None = None,
    ) -> None:
        processed = self._clock_ms() if processed_at_ms is None else processed_at_ms
        self._gesture_latencies.append(max(0.0, processed - feature_timestamp_ms))
        self.gestures_seen += 1

    def snapshot(self) -> TelemetrySnapshot:
        elapsed_ms = 0.0
        if self._started_ms is not None and self._last_received_ms is not None:
            elapsed_ms = max(0.0, self._last_received_ms - self._started_ms)
        effective_fps = self.frames_seen / (elapsed_ms / 1000.0) if elapsed_ms > 0 else 0.0
        return TelemetrySnapshot(
            frames_seen=self.frames_seen,
            hands_seen=self.hands_seen,
            gestures_seen=self.gestures_seen,
            dropped_frames=self.dropped_frames,
            effective_fps=effective_fps,
            mean_frame_interval_ms=(
                sum(self._frame_intervals) / len(self._frame_intervals)
                if self._frame_intervals
                else 0.0
            ),
            mean_frame_age_ms=(
                sum(self._frame_ages) / len(self._frame_ages) if self._frame_ages else 0.0
            ),
            p95_frame_age_ms=_p95(self._frame_ages),
            mean_gesture_latency_ms=(
                sum(self._gesture_latencies) / len(self._gesture_latencies)
                if self._gesture_latencies
                else 0.0
            ),
            p95_gesture_latency_ms=_p95(self._gesture_latencies),
        )


def render_telemetry(snapshot: TelemetrySnapshot) -> str:
    """Render a compact end-of-session report for a terminal or support ticket."""

    return "\n".join(
        [
            "SammyBlaze.wav performance telemetry",
            "Frames: "
            f"{snapshot.frames_seen} | hands: {snapshot.hands_seen} | "
            f"gestures: {snapshot.gestures_seen}",
            f"Dropped frames: {snapshot.dropped_frames}",
            f"Effective FPS: {snapshot.effective_fps:.1f}",
            f"Frame interval ms (mean): {snapshot.mean_frame_interval_ms:.1f}",
            "Frame age ms (mean/p95): "
            f"{snapshot.mean_frame_age_ms:.1f}/{snapshot.p95_frame_age_ms:.1f}",
            "Gesture latency ms (mean/p95): "
            f"{snapshot.mean_gesture_latency_ms:.1f}/{snapshot.p95_gesture_latency_ms:.1f}",
        ]
    )


def save_telemetry(path: str | Path, snapshot: TelemetrySnapshot) -> None:
    """Write a telemetry snapshot atomically so support files are never half-written."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot.as_dict(), indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    temporary.replace(destination)


__all__ = [
    "PerformanceTelemetry",
    "TelemetrySnapshot",
    "render_telemetry",
    "save_telemetry",
]
