"""Versioned, local storage for user-edited SammyBlaze sound presets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from math import isfinite
from pathlib import Path
from typing import Any

from handmusic.music.presets import Preset, get_preset

USER_PRESET_SCHEMA = "sammyblaze.user-sound-preset"
USER_PRESET_SCHEMA_VERSION = 1
USER_PRESET_SUFFIX = ".json"
MAX_PRESET_FILE_BYTES = 128 * 1024
MAX_CUSTOM_NAME_LENGTH = 96

_DOCUMENT_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "source_factory_program_id",
        "custom_name",
        "master_gain",
        "brightness",
        "patch",
    }
)
_PRESET_FIELD_NAMES = tuple(field.name for field in fields(Preset))
_PRESET_FIELD_SET = frozenset(_PRESET_FIELD_NAMES)
_WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_SLUG_SEPARATOR = re.compile(r"[^a-z0-9]+")


class UserPresetError(ValueError):
    """Base error for invalid or unsafe user-preset operations."""


class InvalidUserPresetError(UserPresetError):
    """Raised when a stored document does not match the supported schema."""


class UnsupportedUserPresetVersionError(InvalidUserPresetError):
    """Raised when a document uses an unsupported schema version."""


def _validate_unit_interval(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def normalize_custom_name(custom_name: str) -> str:
    """Return a canonical display name or reject an unsafe filename-like value."""

    if not isinstance(custom_name, str):
        raise TypeError("custom_name must be a string")

    normalized = " ".join(unicodedata.normalize("NFKC", custom_name).split())
    if not normalized:
        raise ValueError("custom_name must not be empty")
    if len(normalized) > MAX_CUSTOM_NAME_LENGTH:
        raise ValueError(f"custom_name must not exceed {MAX_CUSTOM_NAME_LENGTH} characters")
    if normalized in {".", ".."}:
        raise ValueError("custom_name must not be a relative path")
    if any(character in _WINDOWS_FORBIDDEN_CHARACTERS for character in normalized):
        raise ValueError("custom_name contains a filename or path separator character")
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise ValueError("custom_name contains a control character")
    if normalized.endswith((".", " ")):
        raise ValueError("custom_name must not end with a dot or space")

    windows_stem = normalized.split(".", maxsplit=1)[0].upper()
    if windows_stem in _WINDOWS_RESERVED_NAMES:
        raise ValueError("custom_name is reserved by Windows")
    return normalized


def preset_filename(custom_name: str) -> str:
    """Build a deterministic, portable filename without using user input as a path."""

    normalized = normalize_custom_name(custom_name)
    identity = normalized.casefold()
    ascii_name = unicodedata.normalize("NFKD", identity).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_SEPARATOR.sub("-", ascii_name).strip("-")[:48] or "preset"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}{USER_PRESET_SUFFIX}"


def default_preset_directory() -> Path:
    """Return the per-user preset directory without creating it."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data and local_app_data.strip():
        return Path(local_app_data).expanduser() / "SammyBlaze" / "presets"
    return Path.home() / ".sammyblaze" / "presets"


@dataclass(frozen=True, slots=True)
class UserPreset(Preset):
    """A complete editable sound patch with user and factory provenance.

    The class extends :class:`Preset`, so every synthesis field is directly
    available and validated by the factory preset contract. ``master_gain`` and
    ``brightness`` are user-editable renderer controls persisted with the patch.
    """

    source_factory_program_id: int
    custom_name: str
    master_gain: float
    brightness: float

    def __post_init__(self) -> None:
        Preset.__post_init__(self)
        normalized_name = normalize_custom_name(self.custom_name)
        object.__setattr__(self, "custom_name", normalized_name)

        if isinstance(self.source_factory_program_id, bool) or not isinstance(
            self.source_factory_program_id, int
        ):
            raise TypeError("source_factory_program_id must be an integer")
        try:
            get_preset(self.source_factory_program_id)
        except KeyError:
            raise ValueError("source_factory_program_id must identify a factory preset") from None
        if self.program_id != self.source_factory_program_id:
            raise ValueError("program_id must match source_factory_program_id for a user preset")

        _validate_unit_interval("master_gain", self.master_gain)
        _validate_unit_interval("brightness", self.brightness)

    @property
    def patch(self) -> Preset:
        """Return the editable synthesis portion as a validated ``Preset``."""

        return Preset(**{name: getattr(self, name) for name in _PRESET_FIELD_NAMES})

    @classmethod
    def from_factory(
        cls,
        source_factory_program_id: int,
        custom_name: str,
        *,
        master_gain: float = 0.8,
        brightness: float = 0.5,
        **patch_changes: object,
    ) -> UserPreset:
        """Create a user patch from one factory sound plus validated edits."""

        try:
            factory = get_preset(source_factory_program_id)
        except KeyError:
            raise ValueError("source_factory_program_id must identify a factory preset") from None
        unknown_fields = set(patch_changes).difference(_PRESET_FIELD_SET)
        if unknown_fields:
            unknown = ", ".join(sorted(unknown_fields))
            raise TypeError(f"unknown Preset field(s): {unknown}")
        if "program_id" in patch_changes:
            raise ValueError("program_id cannot differ from the source factory preset")

        patch_values = asdict(factory)
        patch_values.update(patch_changes)
        return cls(
            **patch_values,
            source_factory_program_id=source_factory_program_id,
            custom_name=custom_name,
            master_gain=master_gain,
            brightness=brightness,
        )

    def to_document(self) -> dict[str, object]:
        """Return the canonical JSON-compatible schema document."""

        return {
            "schema": USER_PRESET_SCHEMA,
            "schema_version": USER_PRESET_SCHEMA_VERSION,
            "source_factory_program_id": self.source_factory_program_id,
            "custom_name": self.custom_name,
            "master_gain": self.master_gain,
            "brightness": self.brightness,
            "patch": asdict(self.patch),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> UserPreset:
        """Validate and construct a preset from one schema document."""

        if not isinstance(document, Mapping):
            raise InvalidUserPresetError("user preset document must be a JSON object")

        document_keys = frozenset(document)
        if document_keys != _DOCUMENT_KEYS:
            missing = sorted(_DOCUMENT_KEYS.difference(document_keys))
            unknown = sorted(document_keys.difference(_DOCUMENT_KEYS))
            details = []
            if missing:
                details.append(f"missing keys: {', '.join(missing)}")
            if unknown:
                details.append(f"unknown keys: {', '.join(unknown)}")
            raise InvalidUserPresetError(f"invalid user preset document ({'; '.join(details)})")
        if document["schema"] != USER_PRESET_SCHEMA:
            raise InvalidUserPresetError("unsupported user preset schema")

        version = document["schema_version"]
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != USER_PRESET_SCHEMA_VERSION
        ):
            raise UnsupportedUserPresetVersionError(
                f"unsupported user preset schema version: {version!r}"
            )

        patch = document["patch"]
        if not isinstance(patch, Mapping):
            raise InvalidUserPresetError("patch must be a JSON object")
        patch_keys = frozenset(patch)
        if patch_keys != _PRESET_FIELD_SET:
            missing = sorted(_PRESET_FIELD_SET.difference(patch_keys))
            unknown = sorted(patch_keys.difference(_PRESET_FIELD_SET))
            details = []
            if missing:
                details.append(f"missing patch fields: {', '.join(missing)}")
            if unknown:
                details.append(f"unknown patch fields: {', '.join(unknown)}")
            raise InvalidUserPresetError(f"invalid patch ({'; '.join(details)})")

        try:
            return cls(
                **dict(patch),
                source_factory_program_id=document["source_factory_program_id"],
                custom_name=document["custom_name"],
                master_gain=document["master_gain"],
                brightness=document["brightness"],
            )
        except (TypeError, ValueError) as error:
            raise InvalidUserPresetError(f"invalid user preset values: {error}") from error


def _storage_directory(directory: str | os.PathLike[str] | None) -> Path:
    root = default_preset_directory() if directory is None else Path(directory).expanduser()
    return root.resolve(strict=False)


def _preset_path(custom_name: str, directory: str | os.PathLike[str] | None) -> Path:
    root = _storage_directory(directory)
    candidate = root / preset_filename(custom_name)
    if candidate.parent != root:
        raise UserPresetError("preset path escaped the configured preset directory")
    return candidate


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise InvalidUserPresetError(f"duplicate JSON key: {key!r}")
        document[key] = value
    return document


def _reject_non_finite_json(value: str) -> None:
    raise InvalidUserPresetError(f"non-finite JSON number is not allowed: {value}")


def _decode_document(payload: bytes, path: Path) -> UserPreset:
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_json,
        )
        return UserPreset.from_document(document)
    except InvalidUserPresetError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise InvalidUserPresetError(f"invalid user preset file {path.name!r}: {error}") from error


def _load_path(path: Path, root: Path) -> UserPreset:
    if path.is_symlink():
        raise UserPresetError(f"refusing to load symbolic-link preset: {path.name}")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"user preset does not exist: {path.name}") from None
    if resolved.parent != root or not resolved.is_file():
        raise UserPresetError("preset path escaped the configured preset directory")
    if resolved.stat().st_size > MAX_PRESET_FILE_BYTES:
        raise InvalidUserPresetError(
            f"user preset exceeds {MAX_PRESET_FILE_BYTES} bytes: {path.name}"
        )

    preset = _decode_document(resolved.read_bytes(), resolved)
    if preset_filename(preset.custom_name) != resolved.name:
        raise InvalidUserPresetError(
            f"user preset filename does not match custom_name: {resolved.name}"
        )
    return preset


def _sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save_user_preset(
    preset: UserPreset,
    *,
    directory: str | os.PathLike[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Atomically save ``preset`` and return its canonical path.

    With ``overwrite=False``, a same-directory hard link atomically publishes
    the completed temporary file only if the destination does not already
    exist. With ``overwrite=True``, ``os.replace`` atomically swaps the file.
    """

    if not isinstance(preset, UserPreset):
        raise TypeError("preset must be a UserPreset")
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a boolean")

    root = _storage_directory(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = _preset_path(preset.custom_name, root)
    payload = (
        json.dumps(
            preset.to_document(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=root,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        if overwrite:
            os.replace(temporary_path, target)
        else:
            try:
                os.link(temporary_path, target)
            except FileExistsError:
                raise FileExistsError(
                    f"user preset already exists: {preset.custom_name!r}"
                ) from None
            except OSError as error:
                raise UserPresetError(
                    "filesystem could not atomically create the user preset"
                ) from error
        _sync_directory(root)
    finally:
        temporary_path.unlink(missing_ok=True)
    return target


def load_user_preset(
    custom_name: str,
    *,
    directory: str | os.PathLike[str] | None = None,
) -> UserPreset:
    """Load and strictly validate one preset by its custom display name."""

    root = _storage_directory(directory)
    return _load_path(_preset_path(custom_name, root), root)


def list_user_presets(
    *,
    directory: str | os.PathLike[str] | None = None,
) -> tuple[UserPreset, ...]:
    """Return all valid stored presets in deterministic display-name order."""

    root = _storage_directory(directory)
    if not root.exists():
        return ()
    if not root.is_dir():
        raise NotADirectoryError(f"user preset directory is not a directory: {root}")

    paths = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.casefold() == USER_PRESET_SUFFIX
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )
    presets = [_load_path(path, root) for path in paths]
    return tuple(
        sorted(
            presets,
            key=lambda preset: (preset.custom_name.casefold(), preset.custom_name),
        )
    )


def delete_user_preset(
    custom_name: str,
    *,
    directory: str | os.PathLike[str] | None = None,
    missing_ok: bool = False,
) -> bool:
    """Delete one canonical preset file and report whether it existed."""

    if not isinstance(missing_ok, bool):
        raise TypeError("missing_ok must be a boolean")
    root = _storage_directory(directory)
    target = _preset_path(custom_name, root)
    if target.is_symlink():
        raise UserPresetError(f"refusing to delete symbolic-link preset: {target.name}")
    try:
        target.unlink()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise FileNotFoundError(f"user preset does not exist: {custom_name!r}") from None
    _sync_directory(root)
    return True


# Concise aliases for callers already operating inside the user-presets module.
save_preset = save_user_preset
load_preset = load_user_preset
list_presets = list_user_presets
delete_preset = delete_user_preset
