"""PyInstaller hook for SammyBlaze's MediaPipe Tasks Vision runtime.

The upstream wheel loads one shared C library through importlib.resources, which
static binary analysis cannot discover.  Do not collect all of MediaPipe: that
also pulls tests and unrelated task families into the standalone.
"""

from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = collect_dynamic_libs(
    "mediapipe",
    search_patterns=["tasks/c/*.dll"],
)

