from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_VERIFIER_PATH = _ROOT / "packaging" / "windows" / "verify_release_stage.py"
_SPEC = importlib.util.spec_from_file_location("verify_release_stage", _VERIFIER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_VERIFIER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_VERIFIER)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_stage(root: Path, *, version: str = "0.4.0-test") -> dict[str, Any]:
    payloads = {
        "standalone/SammyBlaze/SammyBlaze.exe": b"exe",
        "standalone/SammyBlaze/_internal/SammyBlazeAudioCore.dll": b"dll",
        "standalone/SammyBlaze/_internal/models/hand_landmarker.task": b"model",
        "VST3/SammyBlaze.vst3/Contents/x86_64-win/SammyBlaze.vst3": b"vst",
    }
    files: list[dict[str, Any]] = []
    for relative, content in payloads.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        files.append(
            {
                "path": relative,
                "size": len(content),
                "sha256": _sha256(path),
            }
        )

    manifest = {
        "schemaVersion": 1,
        "product": "SammyBlaze",
        "version": version,
        "platform": "windows-x86_64",
        "configuration": "Release",
        "sourceRevision": "1" * 40,
        "artifacts": {
            "standalone": "standalone/SammyBlaze/SammyBlaze.exe",
            "audioCore": (
                "standalone/SammyBlaze/_internal/SammyBlazeAudioCore.dll"
            ),
            "handModel": (
                "standalone/SammyBlaze/_internal/models/hand_landmarker.task"
            ),
            "vst3": "VST3/SammyBlaze.vst3",
        },
        "files": files,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    checksum_entries = [
        (entry["sha256"], entry["path"]) for entry in manifest["files"]
    ]
    checksum_entries.append((_sha256(manifest_path), "manifest.json"))
    (root / "SHA256SUMS.txt").write_text(
        "".join(f"{digest} *{relative}\n" for digest, relative in checksum_entries),
        encoding="utf-8",
    )
    return manifest


def test_release_stage_verifier_accepts_complete_stage(tmp_path: Path) -> None:
    _write_stage(tmp_path)

    result = _VERIFIER.verify_release_stage(
        tmp_path,
        expected_version="0.4.0-test",
    )

    assert result["passed"] is True
    assert result["manifestFiles"] == 4
    assert result["verifiedChecksums"] == 5


def test_release_stage_verifier_rejects_payload_tampering(tmp_path: Path) -> None:
    _write_stage(tmp_path)
    (tmp_path / "standalone" / "SammyBlaze" / "SammyBlaze.exe").write_bytes(
        b"tampered"
    )

    with pytest.raises(_VERIFIER.StageVerificationError, match="size mismatch"):
        _VERIFIER.verify_release_stage(tmp_path)


def test_release_stage_verifier_rejects_version_mismatch(tmp_path: Path) -> None:
    _write_stage(tmp_path)

    with pytest.raises(_VERIFIER.StageVerificationError, match="version mismatch"):
        _VERIFIER.verify_release_stage(
            tmp_path,
            expected_version="0.5.0",
        )


def test_release_stage_verifier_rejects_traversal(tmp_path: Path) -> None:
    manifest = _write_stage(tmp_path)
    manifest["files"][0]["path"] = "../SammyBlaze.exe"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(_VERIFIER.StageVerificationError, match="safe relative path"):
        _VERIFIER.verify_release_stage(tmp_path)


def test_release_stage_verifier_requires_exact_checksum_coverage(
    tmp_path: Path,
) -> None:
    _write_stage(tmp_path)
    checksum_path = tmp_path / "SHA256SUMS.txt"
    checksum_path.write_text(
        "\n".join(checksum_path.read_text(encoding="utf-8").splitlines()[:-1]) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(_VERIFIER.StageVerificationError, match="coverage mismatch"):
        _VERIFIER.verify_release_stage(tmp_path)


def test_installer_source_keeps_fixed_upgrade_identity_and_safe_defaults() -> None:
    source = (
        _ROOT / "packaging" / "windows" / "installer" / "SammyBlaze.iss"
    ).read_text(encoding="utf-8")

    assert "AppId={{057B9837-B038-4693-8376-0F1EB7FE6524}" in source
    assert "DefaultDirName={autopf}\\SammyBlaze" in source
    assert "PrivilegesRequired=admin" in source
    assert "ArchitecturesAllowed=x64compatible" in source
    assert "{commoncf64}\\VST3" in source
    assert "{param:VST3DIR|}" in source
    assert "Source: \"{#Vst3Source}\\*\"" in source
    assert "DelTree(OldBundle, True, True, True)" in source


def test_native_release_uses_and_checks_static_msvc_runtime() -> None:
    cmake = (_ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    build_script = (
        _ROOT / "packaging" / "windows" / "build-native.ps1"
    ).read_text(encoding="utf-8")

    assert "CMAKE_MSVC_RUNTIME_LIBRARY" in cmake
    assert "MultiThreaded$<$<CONFIG:Debug>:Debug>" in cmake
    assert "SAMMYBLAZE_STATIC_MSVC_RUNTIME" in cmake
    assert "SMTG_USE_STATIC_CRT" in cmake
    assert "Assert-NoDynamicMsvcRuntime" in build_script
    assert "(?:MSVCP|VCRUNTIME)" in build_script
    assert "SAMMYBLAZE_STATIC_MSVC_RUNTIME=OFF" in build_script
    assert "validator-dynamic" in build_script


def test_installer_acceptance_harness_is_isolated_and_opt_in() -> None:
    harness = (
        _ROOT / "packaging" / "windows" / "test-installer.ps1"
    ).read_text(encoding="utf-8")

    assert "AllowMachineMutation" in harness
    assert "SammyBlazeInstallerQA" in harness
    assert '"D:\\VST3"' in harness
    assert '"/CURRENTUSER"' in harness
    assert "Assert-InstalledPayload" in harness
    assert "same-version-repair" in harness
    assert "foreignVstPreserved = $true" in harness
    assert "releaseDecision" in harness


def test_installer_manifest_distinguishes_payload_and_installer_revisions() -> None:
    build_script = (
        _ROOT / "packaging" / "windows" / "build-installer.ps1"
    ).read_text(encoding="utf-8")

    assert "payloadSourceRevision" in build_script
    assert "installerSourceRevision" in build_script
    assert "InstallerSourceRevision must be a 40-character Git SHA" in build_script
