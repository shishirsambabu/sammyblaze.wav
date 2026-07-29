from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

from handmusic.common.models import GestureFeatures


@dataclass(frozen=True, slots=True)
class PerformerPreset:
    """Versioned performer-specific calibration and routing settings."""

    name: str
    neutral_center_x: float
    neutral_center_y: float
    neutral_depth: float
    sensitivity: float = 1.0
    expression_smoothing: float = 0.2
    gesture_confidence: float = 0.7
    camera_index: int = 0
    midi_port: str | None = None
    soundfont: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("preset name cannot be empty")
        for value, label in (
            (self.neutral_center_x, "neutral_center_x"),
            (self.neutral_center_y, "neutral_center_y"),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{label} must be between 0 and 1")
        if self.sensitivity <= 0.0:
            raise ValueError("sensitivity must be positive")
        if not 0.0 < self.expression_smoothing <= 1.0:
            raise ValueError("expression_smoothing must be greater than 0 and no more than 1")
        if not 0.0 <= self.gesture_confidence <= 1.0:
            raise ValueError("gesture_confidence must be between 0 and 1")
        if self.camera_index < 0:
            raise ValueError("camera_index cannot be negative")
        if self.schema_version != 1:
            raise ValueError(f"unsupported preset schema version: {self.schema_version}")


class CalibrationSession:
    """Collect stable hand samples and derive a robust median-based preset."""

    def __init__(self, min_confidence: float = 0.75) -> None:
        self.min_confidence = min_confidence
        self._samples: list[GestureFeatures] = []

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def add(self, features: GestureFeatures) -> bool:
        if features.confidence < self.min_confidence or features.handedness == "unknown":
            return False
        self._samples.append(features)
        return True

    def finalize(
        self,
        name: str,
        *,
        camera_index: int = 0,
        midi_port: str | None = None,
        soundfont: str | None = None,
    ) -> PerformerPreset:
        if not self._samples:
            raise ValueError("at least one confident hand sample is required")
        return PerformerPreset(
            name=name,
            neutral_center_x=float(median(sample.center_x for sample in self._samples)),
            neutral_center_y=float(median(sample.center_y for sample in self._samples)),
            neutral_depth=float(median(sample.depth for sample in self._samples)),
            camera_index=camera_index,
            midi_port=midi_port,
            soundfont=soundfont,
        )


class PresetStore:
    """Read/write JSON presets with atomic replacement and schema validation."""

    @staticmethod
    def save(path: str | Path, preset: PerformerPreset) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(preset), indent=2) + "\n"
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

    @staticmethod
    def load(path: str | Path) -> PerformerPreset:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not read preset: {source}") from exc
        if not isinstance(payload, dict):
            raise ValueError("preset root must be a JSON object")
        try:
            return PerformerPreset(**payload)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid performer preset: {source}") from exc
