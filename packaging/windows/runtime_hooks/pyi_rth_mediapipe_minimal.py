"""Keep unused MediaPipe drawing helpers from requiring Matplotlib at runtime."""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys

_STUBS = frozenset(
    {
        "mediapipe.tasks.python.vision.drawing_styles",
        "mediapipe.tasks.python.vision.drawing_utils",
    }
)


class _MediaPipeDrawingStubLoader(importlib.abc.Loader):
    def create_module(self, spec: object) -> None:
        return None

    def exec_module(self, module: object) -> None:
        module.__doc__ = (
            "Drawing helpers are omitted from the SammyBlaze runtime; "
            "the performer uses its own overlay."
        )


class _MediaPipeDrawingStubFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: object = None,
    ) -> object | None:
        if fullname in _STUBS:
            return importlib.util.spec_from_loader(
                fullname,
                _MediaPipeDrawingStubLoader(),
            )
        return None


sys.meta_path.insert(0, _MediaPipeDrawingStubFinder())

