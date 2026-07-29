from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

from handmusic.music.builtin_synth import BuiltinSynthOutput
from handmusic.music.native_audio_core import NativeAudioCoreOutput

_REQUIRE_NATIVE_ENV = "SAMMYBLAZE_REQUIRE_NATIVE_AUDIO"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class AudioOutputSelection:
    """A selected standalone renderer and the health text shown to the performer."""

    output: Any
    backend_label: str
    warning: str | None = None

    @property
    def native(self) -> bool:
        return isinstance(self.output, NativeAudioCoreOutput)


def native_audio_required() -> bool:
    """Require the shared engine in packaged builds or when explicitly requested."""

    configured = os.environ.get(_REQUIRE_NATIVE_ENV)
    if configured is not None:
        return configured.strip().lower() in _TRUE_VALUES
    return bool(getattr(sys, "frozen", False))


def create_builtin_audio_output(
    program: int = 0,
    block_size: int = 256,
    *,
    require_native: bool | None = None,
) -> AudioOutputSelection:
    """Prefer the shared C++ engine and expose any development fallback."""

    strict = native_audio_required() if require_native is None else require_native
    try:
        output = NativeAudioCoreOutput(program=program, block_size=block_size)
    except Exception as exc:
        if strict:
            raise RuntimeError(
                "The packaged SammyBlaze application requires its native audio "
                f"core, but it could not start: {exc}"
            ) from exc
        fallback = BuiltinSynthOutput(program=program, block_size=block_size)
        return AudioOutputSelection(
            output=fallback,
            backend_label="Python compatibility synth",
            warning=(
                "Native C++ audio core unavailable; Python compatibility synth "
                f"is active ({type(exc).__name__}: {exc})"
            ),
        )
    return AudioOutputSelection(
        output=output,
        backend_label="Native C++ audio core",
    )


__all__ = [
    "AudioOutputSelection",
    "create_builtin_audio_output",
    "native_audio_required",
]
