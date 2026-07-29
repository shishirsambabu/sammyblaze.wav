from __future__ import annotations

from typing import Any

import handmusic.app as app_module


def test_phase9_3_headless_hardware_smoke_suppresses_preview(monkeypatch) -> None:
    received: dict[str, Any] = {}

    def capture_run_camera(
        _runtime: object,
        camera_index: int,
        **kwargs: object,
    ) -> None:
        received["camera_index"] = camera_index
        received.update(kwargs)

    monkeypatch.setattr(app_module, "run_camera", capture_run_camera)

    result = app_module.main(
        [
            "--camera",
            "2",
            "--output",
            "null",
            "--headless",
            "--max-frames",
            "8",
        ]
    )

    assert result == 0
    assert received["camera_index"] == 2
    assert received["max_frames"] == 8
    assert received["display"] is False
