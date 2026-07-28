from __future__ import annotations

import json
import random
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from handmusic.common.models import GestureFeatures

FEATURE_NAMES = (
    "index_open",
    "middle_open",
    "ring_open",
    "pinky_open",
    "thumb_open",
    "pinch_distance",
    "palm_rotation_deg",
    "center_x",
    "center_y",
    "depth",
    "velocity_x",
    "velocity_y",
    "confidence",
)


def feature_vector(features: GestureFeatures) -> tuple[float, ...]:
    return (
        *(float(value) for value in features.fingers_open),
        features.pinch_distance,
        features.palm_rotation_deg,
        features.center_x,
        features.center_y,
        features.depth,
        features.velocity_x,
        features.velocity_y,
        features.confidence,
    )


@dataclass(frozen=True, slots=True)
class GestureSample:
    session_id: str
    timestamp_ms: int
    label: str
    handedness: str
    values: tuple[float, ...]
    metadata: dict[str, str]

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("sample label cannot be empty")
        if len(self.values) != len(FEATURE_NAMES):
            raise ValueError(f"expected {len(FEATURE_NAMES)} feature values")

    @classmethod
    def from_features(
        cls,
        features: GestureFeatures,
        *,
        session_id: str,
        label: str,
        metadata: dict[str, str] | None = None,
    ) -> GestureSample:
        return cls(
            session_id=session_id,
            timestamp_ms=features.timestamp_ms,
            label=label,
            handedness=features.handedness,
            values=feature_vector(features),
            metadata=metadata or {},
        )


class SessionRecorder:
    """Append-only JSONL recorder; it never writes camera frames."""

    def __init__(
        self,
        path: str | Path,
        *,
        session_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or uuid4().hex
        self.metadata = metadata or {}
        self._handle = destination.open("a", encoding="utf-8")

    def record(self, features: GestureFeatures, label: str) -> GestureSample:
        sample = GestureSample.from_features(
            features,
            session_id=self.session_id,
            label=label,
            metadata=self.metadata,
        )
        self._handle.write(json.dumps(asdict(sample), separators=(",", ":")) + "\n")
        self._handle.flush()
        return sample

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self) -> SessionRecorder:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def load_samples(path: str | Path) -> list[GestureSample]:
    samples: list[GestureSample] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                payload["values"] = tuple(payload["values"])
                samples.append(GestureSample(**payload))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid sample at line {line_number}") from exc
    return samples


def split_by_session(
    samples: Iterable[GestureSample],
    *,
    train_ratio: float = 0.7,
    validation_ratio: float = 0.15,
    seed: int = 42,
) -> dict[str, list[GestureSample]]:
    """Split whole sessions so adjacent frames cannot leak across datasets."""
    if not 0.0 < train_ratio < 1.0 or not 0.0 <= validation_ratio < 1.0:
        raise ValueError("split ratios must be between 0 and 1")
    if train_ratio + validation_ratio >= 1.0:
        raise ValueError("train and validation ratios must leave test data")
    grouped: dict[str, list[GestureSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.session_id, []).append(sample)
    sessions = list(grouped)
    random.Random(seed).shuffle(sessions)
    if not sessions:
        return {"train": [], "validation": [], "test": []}
    train_count = max(1, int(len(sessions) * train_ratio))
    validation_count = int(len(sessions) * validation_ratio)
    if len(sessions) >= 3:
        validation_count = max(1, validation_count)
    if train_count + validation_count >= len(sessions):
        validation_count = max(0, len(sessions) - train_count - 1)
    train_sessions = sessions[:train_count]
    validation_sessions = sessions[train_count : train_count + validation_count]
    test_sessions = sessions[train_count + validation_count :]

    def flatten(names: list[str]) -> list[GestureSample]:
        return [sample for name in names for sample in grouped[name]]

    return {
        "train": flatten(train_sessions),
        "validation": flatten(validation_sessions),
        "test": flatten(test_sessions),
    }
