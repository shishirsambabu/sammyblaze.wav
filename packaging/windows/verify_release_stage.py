"""Validate the deterministic Windows release stage before installer compilation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CHECKSUM_RE = re.compile(r"^([0-9a-fA-F]{64}) \*(.+)$")
_REQUIRED_ARTIFACTS = {
    "standalone": "standalone/SammyBlaze/SammyBlaze.exe",
    "audioCore": "standalone/SammyBlaze/_internal/SammyBlazeAudioCore.dll",
    "handModel": "standalone/SammyBlaze/_internal/models/hand_landmarker.task",
    "vst3": "VST3/SammyBlaze.vst3",
}
_REQUIRED_VST_BINARY = (
    "VST3/SammyBlaze.vst3/Contents/x86_64-win/SammyBlaze.vst3"
)


class StageVerificationError(RuntimeError):
    """Raised when a release stage violates the installer input contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise StageVerificationError(f"{label} must be a non-empty string")
    if "\\" in value:
        raise StageVerificationError(f"{label} must use forward slashes: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise StageVerificationError(f"{label} is not a safe relative path: {value!r}")
    return path


def _resolved_child(stage_root: Path, relative: PurePosixPath) -> Path:
    candidate = stage_root.joinpath(*relative.parts).resolve()
    if not candidate.is_relative_to(stage_root):
        raise StageVerificationError(f"path escapes the release stage: {relative}")
    return candidate


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageVerificationError(f"cannot read release manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise StageVerificationError("release manifest root must be an object")
    return payload


def _verify_manifest_header(
    manifest: dict[str, Any],
    *,
    expected_version: str | None,
) -> tuple[str, str]:
    if manifest.get("schemaVersion") != 1:
        raise StageVerificationError("release manifest schemaVersion must be 1")
    if manifest.get("product") != "SammyBlaze":
        raise StageVerificationError("release manifest product must be SammyBlaze")
    if manifest.get("platform") != "windows-x86_64":
        raise StageVerificationError("release manifest platform must be windows-x86_64")
    if manifest.get("configuration") != "Release":
        raise StageVerificationError("release manifest configuration must be Release")

    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise StageVerificationError("release manifest version is missing")
    if expected_version is not None and version != expected_version:
        raise StageVerificationError(
            f"release version mismatch: expected {expected_version!r}, found {version!r}"
        )

    revision = manifest.get("sourceRevision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise StageVerificationError(
            "release manifest sourceRevision must be a 40-character Git SHA"
        )
    return version, revision.lower()


def _verify_artifact_contract(manifest: dict[str, Any], stage_root: Path) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise StageVerificationError("release manifest artifacts must be an object")
    for name, expected in _REQUIRED_ARTIFACTS.items():
        if artifacts.get(name) != expected:
            raise StageVerificationError(
                f"release artifact {name!r} must be {expected!r}"
            )

    for name, relative_value in _REQUIRED_ARTIFACTS.items():
        relative = _safe_relative_path(relative_value, label=f"artifact {name}")
        path = _resolved_child(stage_root, relative)
        expected_kind = "directory" if name == "vst3" else "file"
        valid = path.is_dir() if name == "vst3" else path.is_file()
        if not valid:
            raise StageVerificationError(
                f"required {expected_kind} is missing: {relative_value}"
            )

    vst_binary = _resolved_child(
        stage_root,
        _safe_relative_path(_REQUIRED_VST_BINARY, label="VST3 binary"),
    )
    if not vst_binary.is_file():
        raise StageVerificationError(
            f"required VST3 binary is missing: {_REQUIRED_VST_BINARY}"
        )


def _verify_manifest_files(
    manifest: dict[str, Any],
    stage_root: Path,
) -> set[str]:
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise StageVerificationError("release manifest files must be a non-empty list")

    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise StageVerificationError(f"manifest file entry {index} must be an object")
        relative = _safe_relative_path(
            entry.get("path"),
            label=f"manifest file entry {index}",
        )
        relative_text = relative.as_posix()
        if relative_text in seen:
            raise StageVerificationError(
                f"duplicate manifest file path: {relative_text}"
            )
        seen.add(relative_text)

        size = entry.get("size")
        expected_hash = entry.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise StageVerificationError(
                f"manifest file size is invalid: {relative_text}"
            )
        if not isinstance(expected_hash, str) or not _SHA256_RE.fullmatch(
            expected_hash
        ):
            raise StageVerificationError(
                f"manifest file SHA-256 is invalid: {relative_text}"
            )

        path = _resolved_child(stage_root, relative)
        if not path.is_file():
            raise StageVerificationError(f"manifest file is missing: {relative_text}")
        if path.stat().st_size != size:
            raise StageVerificationError(f"manifest file size mismatch: {relative_text}")
        if _sha256(path) != expected_hash:
            raise StageVerificationError(
                f"manifest file SHA-256 mismatch: {relative_text}"
            )

    if _REQUIRED_VST_BINARY not in seen:
        raise StageVerificationError("manifest does not cover the VST3 binary")
    return seen


def _verify_checksum_file(
    checksum_path: Path,
    stage_root: Path,
    manifest_files: set[str],
) -> int:
    try:
        lines = checksum_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise StageVerificationError(f"cannot read SHA256SUMS.txt: {exc}") from exc
    if not lines:
        raise StageVerificationError("SHA256SUMS.txt is empty")

    expected_paths = manifest_files | {"manifest.json"}
    seen: set[str] = set()
    for index, line in enumerate(lines, start=1):
        match = _CHECKSUM_RE.fullmatch(line)
        if match is None:
            raise StageVerificationError(
                f"malformed SHA256SUMS.txt line {index}: {line!r}"
            )
        expected_hash, relative_value = match.groups()
        relative = _safe_relative_path(
            relative_value,
            label=f"SHA256SUMS.txt line {index}",
        )
        relative_text = relative.as_posix()
        if relative_text in seen:
            raise StageVerificationError(
                f"duplicate checksum path: {relative_text}"
            )
        seen.add(relative_text)
        path = _resolved_child(stage_root, relative)
        if not path.is_file():
            raise StageVerificationError(f"checksummed file is missing: {relative_text}")
        if _sha256(path) != expected_hash.lower():
            raise StageVerificationError(
                f"SHA256SUMS.txt mismatch: {relative_text}"
            )

    missing = sorted(expected_paths - seen)
    unexpected = sorted(seen - expected_paths)
    if missing or unexpected:
        raise StageVerificationError(
            "SHA256SUMS.txt coverage mismatch: "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )
    return len(seen)


def verify_release_stage(
    stage: Path,
    *,
    expected_version: str | None = None,
) -> dict[str, Any]:
    """Verify a release stage and return a compact machine-readable summary."""

    stage_root = stage.resolve()
    if not stage_root.is_dir():
        raise StageVerificationError(f"release stage is missing: {stage_root}")

    manifest_path = stage_root / "manifest.json"
    checksum_path = stage_root / "SHA256SUMS.txt"
    if not manifest_path.is_file():
        raise StageVerificationError(f"release manifest is missing: {manifest_path}")
    if not checksum_path.is_file():
        raise StageVerificationError(f"release checksums are missing: {checksum_path}")

    manifest = _load_manifest(manifest_path)
    version, revision = _verify_manifest_header(
        manifest,
        expected_version=expected_version,
    )
    _verify_artifact_contract(manifest, stage_root)
    manifest_files = _verify_manifest_files(manifest, stage_root)
    checksum_count = _verify_checksum_file(
        checksum_path,
        stage_root,
        manifest_files,
    )
    return {
        "schema": "sammyblaze.release-stage-verification",
        "schemaVersion": 1,
        "passed": True,
        "version": version,
        "sourceRevision": revision,
        "manifestFiles": len(manifest_files),
        "verifiedChecksums": checksum_count,
        "stageRoot": str(stage_root),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--expected-version")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = verify_release_stage(
            args.stage,
            expected_version=args.expected_version,
        )
    except StageVerificationError as exc:
        print(
            json.dumps(
                {
                    "schema": "sammyblaze.release-stage-verification",
                    "schemaVersion": 1,
                    "passed": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
