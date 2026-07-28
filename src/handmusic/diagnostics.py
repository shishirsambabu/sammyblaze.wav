from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

_DISTRIBUTIONS = {
    "sammyblaze-wav": "application",
    "numpy": "numpy",
    "PyYAML": "yaml",
    "mido": "mido",
    "python-rtmidi": "python-rtmidi",
    "opencv-python": "opencv-python",
    "mediapipe": "mediapipe",
    "scikit-learn": "scikit-learn",
}


def _installed_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def collect_diagnostics(model_path: str | Path = "models/hand_landmarker.task") -> dict[str, Any]:
    """Collect support-safe runtime information without opening hardware outputs."""

    model = Path(model_path).expanduser()
    try:
        resolved_model = str(model.resolve())
    except OSError:
        resolved_model = str(model)
    model_info: dict[str, Any] = {
        "path": resolved_model,
        "exists": model.is_file(),
        "size_bytes": model.stat().st_size if model.is_file() else None,
    }

    dependencies = {
        label: _installed_version(distribution)
        for distribution, label in _DISTRIBUTIONS.items()
    }
    midi: dict[str, Any] = {
        "mido": dependencies["mido"],
        "python-rtmidi": dependencies["python-rtmidi"],
        "output_ports": None,
        "port_error": None,
    }
    try:
        import mido

        try:
            midi["output_ports"] = list(mido.get_output_names())
        except Exception as exc:  # pragma: no cover - depends on host MIDI drivers
            midi["port_error"] = f"{type(exc).__name__}: {exc}"
    except ImportError:
        midi["port_error"] = "Mido is not installed"

    return {
        "application": {
            "version": dependencies["application"],
            "working_directory": str(Path.cwd()),
        },
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "model": model_info,
        "dependencies": dependencies,
        "midi": midi,
    }


def render_diagnostics(report: dict[str, Any]) -> str:
    """Render a stable, copy/paste-friendly support report."""

    application = report["application"]
    runtime = report["runtime"]
    model = report["model"]
    dependencies = report["dependencies"]
    midi = report["midi"]
    lines = [
        "SammyBlaze.wav diagnostics",
        f"Application: {application['version'] or 'editable/unknown'}",
        f"Python: {runtime['python']} ({runtime['implementation']})",
        f"Platform: {runtime['platform']}",
        f"Executable: {runtime['executable']}",
        f"Working directory: {application['working_directory']}",
        f"Hand model: {'OK' if model['exists'] else 'MISSING'} ({model['path']})",
    ]
    if model["size_bytes"] is not None:
        lines.append(f"Hand model bytes: {model['size_bytes']}")
    lines.append("Dependencies:")
    for label, installed in dependencies.items():
        lines.append(f"  {label}: {installed or 'missing'}")
    lines.append(f"MIDI output ports: {midi['output_ports'] or 'none detected'}")
    if midi["port_error"]:
        lines.append(f"MIDI port probe: {midi['port_error']}")
    return "\n".join(lines)


__all__ = ["collect_diagnostics", "render_diagnostics"]
