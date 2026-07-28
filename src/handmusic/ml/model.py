from __future__ import annotations

from typing import Any

from .recording import GestureSample


def train_random_forest(samples: list[GestureSample], *, seed: int = 42) -> Any:
    """Train a small optional baseline; rules remain the production baseline."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install the [ml] extra to train the optional baseline") from exc
    if not samples:
        raise ValueError("at least one training sample is required")
    model = RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=-1)
    model.fit([sample.values for sample in samples], [sample.label for sample in samples])
    return model
