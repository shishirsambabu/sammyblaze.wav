"""Post-build assertions and footprint reporting for the Windows standalone."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from pathlib import Path

REQUIRED_EXACT_FILES = (
    "SammyBlaze.exe",
    "_internal/SammyBlazeAudioCore.dll",
    "_internal/models/hand_landmarker.task",
    "_internal/mediapipe/tasks/c/libmediapipe.dll",
    "_internal/PySide6/Qt6Core.dll",
    "_internal/PySide6/Qt6Gui.dll",
    "_internal/PySide6/Qt6Widgets.dll",
    "_internal/PySide6/plugins/platforms/qwindows.dll",
    "_internal/_sounddevice_data/portaudio-binaries/libportaudio64bit.dll",
)
REQUIRED_FILE_GLOBS = (
    "_internal/cv2/cv2*.pyd",
    "_internal/cv2/opencv_videoio_ffmpeg*_64.dll",
    "_internal/rtmidi/*.pyd",
)
REQUIRED_MODULES = frozenset(
    {
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "cv2",
        "mediapipe",
        "mediapipe.tasks.python.core.mediapipe_c_bindings",
        "mediapipe.tasks.python.vision.hand_landmarker",
        "mido.backends.rtmidi",
        "numpy",
        "rtmidi",
        "sounddevice",
    }
)
FORBIDDEN_MODULE_PREFIXES = (
    "IPython",
    "PIL",
    "jax",
    "jupyter",
    "matplotlib",
    "mpl_toolkits",
    "notebook",
    "pytest",
    "scipy",
    "tensorflow",
    "torch",
)


def _walk_toc(value: object) -> Iterable[tuple[object, ...]]:
    if isinstance(value, tuple):
        yield value
        for item in value:
            yield from _walk_toc(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_toc(item)
    elif isinstance(value, dict):
        for item in value.items():
            yield from _walk_toc(item)


def modules_from_analysis_toc(path: Path) -> set[str]:
    value = ast.literal_eval(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for item in _walk_toc(value):
        if len(item) < 3 or not isinstance(item[0], str):
            continue
        name, _source, entry_type = item[:3]
        if entry_type == "PYMODULE":
            modules.add(name)
        elif entry_type in {"BINARY", "EXTENSION"} and name.lower().endswith(".pyd"):
            modules.add(name[:-4].replace("\\", ".").replace("/", "."))
    return modules


def bundle_metrics(bundle: Path) -> tuple[int, int]:
    files = [path for path in bundle.rglob("*") if path.is_file()]
    return sum(path.stat().st_size for path in files), len(files)


def verify_bundle(
    bundle: Path,
    analysis_toc: Path,
    baseline_bytes: int,
    max_bytes: int = 450_000_000,
    max_files: int = 1_500,
) -> tuple[int, int]:
    if not bundle.is_dir():
        raise RuntimeError(f"bundle is missing: {bundle}")
    if not analysis_toc.is_file():
        raise RuntimeError(f"PyInstaller analysis TOC is missing: {analysis_toc}")

    missing_files = [
        relative
        for relative in REQUIRED_EXACT_FILES
        if not (bundle / Path(relative)).is_file()
    ]
    for pattern in REQUIRED_FILE_GLOBS:
        if not any(bundle.glob(pattern)):
            missing_files.append(pattern)
    if missing_files:
        raise RuntimeError("required bundle files are missing: " + ", ".join(missing_files))

    modules = modules_from_analysis_toc(analysis_toc)
    missing_modules = sorted(REQUIRED_MODULES - modules)
    if missing_modules:
        raise RuntimeError("required frozen modules are missing: " + ", ".join(missing_modules))
    forbidden_modules = sorted(
        module
        for module in modules
        if module.startswith(FORBIDDEN_MODULE_PREFIXES)
    )
    if forbidden_modules:
        raise RuntimeError(
            "excluded module stacks leaked into the bundle: "
            + ", ".join(forbidden_modules[:20])
        )

    bundle_bytes, file_count = bundle_metrics(bundle)
    if bundle_bytes >= baseline_bytes:
        raise RuntimeError(
            f"bundle did not shrink: {bundle_bytes} bytes versus {baseline_bytes} baseline"
        )
    if bundle_bytes > max_bytes:
        raise RuntimeError(
            f"bundle exceeds the absolute size gate: {bundle_bytes} > {max_bytes} bytes"
        )
    if file_count > max_files:
        raise RuntimeError(
            f"bundle exceeds the absolute file-count gate: {file_count} > {max_files}"
        )
    saved_bytes = baseline_bytes - bundle_bytes
    reduction = saved_bytes / baseline_bytes * 100.0
    print(
        "BUNDLE_METRICS "
        f"bytes={bundle_bytes} files={file_count} "
        f"saved_bytes={saved_bytes} reduction_percent={reduction:.2f}"
    )
    return bundle_bytes, file_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--analysis-toc", type=Path, required=True)
    parser.add_argument("--baseline-bytes", type=int, required=True)
    parser.add_argument("--max-bytes", type=int, default=450_000_000)
    parser.add_argument("--max-files", type=int, default=1_500)
    args = parser.parse_args()
    verify_bundle(
        args.bundle,
        args.analysis_toc,
        args.baseline_bytes,
        args.max_bytes,
        args.max_files,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
