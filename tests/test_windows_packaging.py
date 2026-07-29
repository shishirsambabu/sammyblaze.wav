from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_VERIFIER_PATH = _ROOT / "packaging" / "windows" / "verify_bundle.py"
_SPEC = importlib.util.spec_from_file_location("verify_bundle", _VERIFIER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_VERIFIER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_VERIFIER)


def _write_analysis(path: Path, modules: set[str]) -> None:
    entries = [(module, f"{module}.py", "PYMODULE") for module in sorted(modules)]
    path.write_text(repr(([], [], [], entries)), encoding="utf-8")


def _make_required_bundle(bundle: Path) -> None:
    for relative in _VERIFIER.REQUIRED_EXACT_FILES:
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    for relative in (
        "_internal/cv2/cv2.cp312-win_amd64.pyd",
        "_internal/cv2/opencv_videoio_ffmpeg500_64.dll",
        "_internal/rtmidi/_rtmidi.cp312-win_amd64.pyd",
    ):
        path = bundle / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


def test_bundle_verifier_accepts_minimal_required_payload(tmp_path: Path) -> None:
    bundle = tmp_path / "SammyBlaze"
    _make_required_bundle(bundle)
    toc = tmp_path / "Analysis-00.toc"
    _write_analysis(toc, set(_VERIFIER.REQUIRED_MODULES))

    bundle_bytes, file_count = _VERIFIER.verify_bundle(bundle, toc, 10_000)

    assert bundle_bytes == file_count
    assert file_count > 10


@pytest.mark.parametrize("entry_type", ("BINARY", "EXTENSION"))
def test_analysis_toc_maps_pyside_binary_extensions_to_modules(
    tmp_path: Path,
    entry_type: str,
) -> None:
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(
        repr(
            (
                [],
                [
                    (
                        "PySide6\\QtWidgets.pyd",
                        "PySide6\\QtWidgets.pyd",
                        entry_type,
                    )
                ],
            )
        ),
        encoding="utf-8",
    )

    assert "PySide6.QtWidgets" in _VERIFIER.modules_from_analysis_toc(toc)


def test_bundle_verifier_enforces_absolute_size_gate(tmp_path: Path) -> None:
    bundle = tmp_path / "SammyBlaze"
    _make_required_bundle(bundle)
    toc = tmp_path / "Analysis-00.toc"
    _write_analysis(toc, set(_VERIFIER.REQUIRED_MODULES))

    with pytest.raises(RuntimeError, match="absolute size gate"):
        _VERIFIER.verify_bundle(bundle, toc, 10_000, max_bytes=1)


def test_bundle_verifier_enforces_absolute_file_gate(tmp_path: Path) -> None:
    bundle = tmp_path / "SammyBlaze"
    _make_required_bundle(bundle)
    toc = tmp_path / "Analysis-00.toc"
    _write_analysis(toc, set(_VERIFIER.REQUIRED_MODULES))

    with pytest.raises(RuntimeError, match="absolute file-count gate"):
        _VERIFIER.verify_bundle(bundle, toc, 10_000, max_files=1)


@pytest.mark.parametrize("prefix", _VERIFIER.FORBIDDEN_MODULE_PREFIXES)
def test_bundle_verifier_rejects_excluded_stacks(
    tmp_path: Path,
    prefix: str,
) -> None:
    bundle = tmp_path / "SammyBlaze"
    _make_required_bundle(bundle)
    toc = tmp_path / "Analysis-00.toc"
    _write_analysis(toc, set(_VERIFIER.REQUIRED_MODULES) | {f"{prefix}.unused"})

    with pytest.raises(RuntimeError, match="excluded module stacks leaked"):
        _VERIFIER.verify_bundle(bundle, toc, 10_000)
