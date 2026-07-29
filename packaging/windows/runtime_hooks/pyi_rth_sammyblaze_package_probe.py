"""Opt-in release probe that executes inside the frozen application."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _run_probe(result_path: Path) -> None:
    result: dict[str, object] = {"status": "starting"}
    try:
        import cv2
        import mediapipe
        import mido.backends.rtmidi as midi_backend
        import rtmidi
        import sounddevice
        from PySide6.QtWidgets import QApplication

        from handmusic.music.native_audio_core import load_native_audio_core
        from handmusic.tracking.hand_tracker import MediaPipeHandTracker

        _ = QApplication.instance()
        sounddevice.query_devices()

        tracker = MediaPipeHandTracker()
        tracker.close()

        _library, bindings, _library_path = load_native_audio_core()
        handle = bindings.create(48000.0, 256)
        if not handle:
            raise RuntimeError("native audio core returned a null handle")
        bindings.destroy(handle)

        result.update(
            {
                "status": "ok",
                "pyside6": "widgets",
                "opencv": cv2.__version__,
                "mediapipe": mediapipe.__version__,
                "sounddevice": sounddevice.__version__,
                "midi": rtmidi.__version__,
                "midoBackend": midi_backend.__name__,
                "nativeAudioAbi": int(bindings.abi_version()),
            }
        )
    except Exception as exc:
        result.update(
            {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


_probe_path = os.environ.get("SAMMYBLAZE_PACKAGE_PROBE")
if _probe_path:
    _run_probe(Path(_probe_path))

