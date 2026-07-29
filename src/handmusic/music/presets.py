"""Deterministic factory preset catalog for the SammyBlaze synthesis engines.

The catalog deliberately contains synthesis parameters rather than samples or
engine-specific objects.  That keeps the preset IDs and musical intent stable
across the Python standalone instrument, the native plug-in, and future render
engines.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType

CATEGORIES = (
    "keys",
    "basses",
    "leads",
    "plucks",
    "bells",
    "polysynths",
    "pads",
    "atmospheres",
    "motion_textures",
    "cinematic",
)

WAVEFORMS = frozenset(
    {
        "sine",
        "triangle",
        "saw",
        "square",
        "pulse",
        "organ",
        "metal",
        "noise",
        "vocal",
        "wavetable",
    }
)
FILTER_TYPES = frozenset({"lowpass", "highpass", "bandpass", "notch"})


def _require_number(name: str, value: float, minimum: float, maximum: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    if not isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True, slots=True)
class Preset:
    """A renderer-independent, immutable synthesis preset.

    Time values use milliseconds, oscillator mix is the proportion of
    ``waveform_b``, and all effect mix values are normalized from 0 to 1.
    """

    program_id: int
    midi_program: int
    category: str
    name: str
    waveform_a: str
    waveform_b: str
    waveform_mix: float
    attack_ms: float
    decay_ms: float
    sustain: float
    release_ms: float
    filter_type: str
    filter_cutoff_hz: float
    filter_resonance: float
    filter_envelope: float
    detune_cents: float
    unison_voices: int
    vibrato_rate_hz: float
    vibrato_depth_semitones: float
    reverb_mix: float
    delay_mix: float
    delay_time_ms: float
    chorus_mix: float

    def __post_init__(self) -> None:
        self.validate()

    @property
    def waveform(self) -> str:
        """Human-readable oscillator pairing."""

        return f"{self.waveform_a}/{self.waveform_b}"

    @property
    def adsr(self) -> tuple[float, float, float, float]:
        """Attack, decay, sustain, and release in renderer-ready order."""

        return self.attack_ms, self.decay_ms, self.sustain, self.release_ms

    @property
    def synthesis_signature(self) -> tuple[object, ...]:
        """Musical parameters used to detect accidental alias presets."""

        return (
            self.waveform_a,
            self.waveform_b,
            self.waveform_mix,
            *self.adsr,
            self.filter_type,
            self.filter_cutoff_hz,
            self.filter_resonance,
            self.filter_envelope,
            self.detune_cents,
            self.unison_voices,
            self.vibrato_rate_hz,
            self.vibrato_depth_semitones,
            self.reverb_mix,
            self.delay_mix,
            self.delay_time_ms,
            self.chorus_mix,
        )

    def validate(self) -> None:
        """Raise a descriptive exception when a preset is not render-safe."""

        if isinstance(self.program_id, bool) or not isinstance(self.program_id, int):
            raise TypeError("program_id must be an integer")
        if not 0 <= self.program_id <= 16_383:
            raise ValueError("program_id must be between 0 and 16383")
        if isinstance(self.midi_program, bool) or not isinstance(self.midi_program, int):
            raise TypeError("midi_program must be an integer")
        if not 0 <= self.midi_program <= 127:
            raise ValueError("midi_program must be between 0 and 127")
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown preset category: {self.category!r}")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.waveform_a not in WAVEFORMS or self.waveform_b not in WAVEFORMS:
            raise ValueError("waveforms must be supported oscillator shapes")
        if self.filter_type not in FILTER_TYPES:
            raise ValueError(f"unsupported filter type: {self.filter_type!r}")
        if (
            isinstance(self.unison_voices, bool)
            or not isinstance(self.unison_voices, int)
            or not 1 <= self.unison_voices <= 16
        ):
            raise ValueError("unison_voices must be an integer between 1 and 16")

        _require_number("waveform_mix", self.waveform_mix, 0.0, 1.0)
        _require_number("attack_ms", self.attack_ms, 0.0, 20_000.0)
        _require_number("decay_ms", self.decay_ms, 0.0, 20_000.0)
        _require_number("sustain", self.sustain, 0.0, 1.0)
        _require_number("release_ms", self.release_ms, 0.0, 30_000.0)
        _require_number("filter_cutoff_hz", self.filter_cutoff_hz, 20.0, 20_000.0)
        _require_number("filter_resonance", self.filter_resonance, 0.0, 1.0)
        _require_number("filter_envelope", self.filter_envelope, -1.0, 1.0)
        _require_number("detune_cents", self.detune_cents, 0.0, 100.0)
        _require_number("vibrato_rate_hz", self.vibrato_rate_hz, 0.0, 15.0)
        _require_number(
            "vibrato_depth_semitones",
            self.vibrato_depth_semitones,
            0.0,
            2.0,
        )
        _require_number("reverb_mix", self.reverb_mix, 0.0, 1.0)
        _require_number("delay_mix", self.delay_mix, 0.0, 1.0)
        _require_number("delay_time_ms", self.delay_time_ms, 1.0, 2_500.0)
        _require_number("chorus_mix", self.chorus_mix, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class _Family:
    names: tuple[str, ...]
    midi_programs: tuple[int, ...]
    wave_pairs: tuple[tuple[str, str], ...]
    filter_types: tuple[str, ...]
    attack: tuple[float, float]
    decay: tuple[float, float]
    sustain: tuple[float, float]
    release: tuple[float, float]
    cutoff: tuple[float, float]
    resonance: tuple[float, float]
    filter_envelope: tuple[float, float]
    detune: tuple[float, float]
    unison: tuple[int, int]
    vibrato_rate: tuple[float, float]
    vibrato_depth: tuple[float, float]
    reverb: tuple[float, float]
    delay: tuple[float, float]
    delay_time: tuple[float, float]
    chorus: tuple[float, float]


_FAMILIES = {
    "keys": _Family(
        (
            "Studio Grand",
            "Velvet Upright",
            "Glass Rhodes",
            "Midnight Tines",
            "Copper Wurlitzer",
            "Tape Pianette",
            "Neon Clavinet",
            "Soft Felt Keys",
            "Chorus Electric Piano",
            "Crystal Harpsichord",
            "Lo-Fi Keybed",
            "Celestial Keys",
        ),
        (0, 1, 4, 5, 4, 3, 7, 0, 5, 6, 2, 88),
        (("triangle", "sine"), ("sine", "metal"), ("triangle", "organ")),
        ("lowpass", "bandpass"),
        (2.0, 55.0),
        (180.0, 1_600.0),
        (0.22, 0.78),
        (180.0, 2_400.0),
        (1_600.0, 12_000.0),
        (0.05, 0.46),
        (-0.12, 0.48),
        (0.0, 9.0),
        (1, 4),
        (3.8, 6.2),
        (0.0, 0.18),
        (0.04, 0.42),
        (0.0, 0.24),
        (90.0, 520.0),
        (0.0, 0.38),
    ),
    "basses": _Family(
        (
            "Sub Monarch",
            "Rubber Current",
            "Analog Anchor",
            "Acid Prowler",
            "Electric Pulse Bass",
            "FM Quarry",
            "Reese Horizon",
            "Plucked Lowline",
            "Darkside Bass",
            "Growl Circuit",
            "Voltage Bass",
            "Cinematic Sub",
        ),
        (38, 39, 32, 38, 33, 39, 39, 36, 35, 39, 38, 39),
        (("sine", "saw"), ("triangle", "square"), ("saw", "pulse"), ("sine", "metal")),
        ("lowpass", "bandpass"),
        (1.0, 35.0),
        (80.0, 760.0),
        (0.42, 0.98),
        (55.0, 620.0),
        (90.0, 3_800.0),
        (0.12, 0.82),
        (-0.18, 0.72),
        (0.0, 24.0),
        (1, 6),
        (3.0, 6.8),
        (0.0, 0.16),
        (0.0, 0.22),
        (0.0, 0.2),
        (65.0, 390.0),
        (0.0, 0.34),
    ),
    "leads": _Family(
        (
            "Solar Monosynth",
            "Singing Square",
            "Razor Ribbon",
            "Portamento Glass",
            "Aurora Lead",
            "Brassfire Solo",
            "Pulse Voyager",
            "Harmonic Flute",
            "Electric Soprano",
            "Sync Serpent",
            "Dreamcaster Lead",
            "Arena Anthem",
        ),
        (80, 81, 81, 98, 80, 62, 81, 73, 85, 84, 85, 81),
        (("saw", "square"), ("pulse", "triangle"), ("sine", "vocal"), ("saw", "metal")),
        ("lowpass", "bandpass", "highpass"),
        (2.0, 95.0),
        (90.0, 820.0),
        (0.58, 1.0),
        (90.0, 1_050.0),
        (700.0, 14_000.0),
        (0.08, 0.72),
        (-0.12, 0.66),
        (0.0, 28.0),
        (1, 8),
        (4.1, 7.8),
        (0.08, 0.72),
        (0.04, 0.52),
        (0.02, 0.46),
        (80.0, 690.0),
        (0.0, 0.48),
    ),
    "plucks": _Family(
        (
            "Walnut Pluck",
            "Digital Koto",
            "Prism Marimba",
            "Rubber Kalimba",
            "Sequencer Pick",
            "Frosted String",
            "Neon Droplet",
            "Muted Circuit",
            "Sunlit Pizzicato",
            "Bamboo Pulse",
            "Elastic Harp",
            "Stardust Pluck",
        ),
        (24, 107, 12, 108, 80, 45, 98, 28, 45, 15, 46, 99),
        (("triangle", "saw"), ("sine", "metal"), ("square", "noise"), ("sine", "pulse")),
        ("lowpass", "bandpass", "highpass"),
        (0.0, 14.0),
        (55.0, 920.0),
        (0.0, 0.26),
        (45.0, 1_300.0),
        (550.0, 15_000.0),
        (0.04, 0.72),
        (0.18, 0.92),
        (0.0, 15.0),
        (1, 5),
        (3.2, 7.2),
        (0.0, 0.12),
        (0.02, 0.46),
        (0.0, 0.4),
        (55.0, 480.0),
        (0.0, 0.3),
    ),
    "bells": _Family(
        (
            "Silver Handbell",
            "FM Temple Bell",
            "Glass Carillon",
            "Ice Celesta",
            "Bronze Halo",
            "Music Box Moon",
            "Crystal Chime",
            "Tubular Dawn",
            "Digital Gamelan",
            "Shimmer Bell",
            "Broken Toy Bell",
            "Deep Space Bell",
        ),
        (9, 14, 14, 8, 14, 10, 9, 14, 9, 98, 10, 99),
        (("sine", "metal"), ("triangle", "metal"), ("sine", "noise")),
        ("bandpass", "highpass", "lowpass"),
        (0.0, 12.0),
        (380.0, 4_800.0),
        (0.0, 0.14),
        (520.0, 7_500.0),
        (1_100.0, 17_500.0),
        (0.08, 0.76),
        (-0.08, 0.45),
        (0.0, 11.0),
        (1, 5),
        (4.0, 8.8),
        (0.0, 0.22),
        (0.18, 0.72),
        (0.02, 0.46),
        (120.0, 920.0),
        (0.0, 0.42),
    ),
    "polysynths": _Family(
        (
            "Classic Poly Eight",
            "Satin Poly",
            "Brass Matrix",
            "Vintage Pulse Stack",
            "Neon Poly Chord",
            "Sync Panorama",
            "Soft Analog Ensemble",
            "Digital Superstack",
            "Warm Saw Choir",
            "Prism Poly",
            "Retro Film Synth",
            "Wide Horizon Poly",
        ),
        (90, 89, 62, 90, 90, 84, 89, 91, 90, 91, 89, 90),
        (("saw", "pulse"), ("square", "triangle"), ("saw", "organ"), ("pulse", "wavetable")),
        ("lowpass", "bandpass", "notch"),
        (4.0, 110.0),
        (130.0, 1_350.0),
        (0.42, 0.96),
        (170.0, 2_100.0),
        (480.0, 13_500.0),
        (0.08, 0.68),
        (-0.16, 0.72),
        (2.0, 32.0),
        (2, 10),
        (3.4, 7.1),
        (0.0, 0.28),
        (0.04, 0.46),
        (0.0, 0.38),
        (80.0, 610.0),
        (0.04, 0.64),
    ),
    "pads": _Family(
        (
            "Warm Cloud Pad",
            "Velvet Strings Pad",
            "Lunar Choir Pad",
            "Analog Sunrise",
            "Frozen Glass Pad",
            "Oceanic Pad",
            "Ember Pad",
            "Slow Brass Canopy",
            "Dream Tape Pad",
            "Cathedral Air Pad",
            "Aurora String Pad",
            "Infinite Bloom Pad",
        ),
        (89, 48, 91, 89, 92, 94, 95, 61, 89, 91, 50, 88),
        (("saw", "vocal"), ("triangle", "organ"), ("wavetable", "sine"), ("saw", "noise")),
        ("lowpass", "bandpass", "notch"),
        (280.0, 4_600.0),
        (650.0, 5_600.0),
        (0.54, 1.0),
        (1_300.0, 11_000.0),
        (240.0, 9_500.0),
        (0.04, 0.58),
        (-0.34, 0.44),
        (5.0, 46.0),
        (3, 12),
        (0.18, 5.8),
        (0.02, 0.46),
        (0.22, 0.78),
        (0.0, 0.42),
        (140.0, 1_100.0),
        (0.14, 0.72),
    ),
    "atmospheres": _Family(
        (
            "Distant Rainlight",
            "Orbital Dust",
            "Empty Cathedral",
            "Underwater Signals",
            "Polar Night Air",
            "Forest Haze",
            "Radio Nebula",
            "Desert Stars",
            "Glass Horizon",
            "Subterranean Wind",
            "Cloud Chamber",
            "Afterglow Field",
        ),
        (96, 103, 91, 99, 101, 96, 103, 96, 99, 100, 102, 97),
        (("noise", "sine"), ("wavetable", "noise"), ("vocal", "metal"), ("organ", "noise")),
        ("bandpass", "highpass", "lowpass", "notch"),
        (620.0, 7_200.0),
        (1_100.0, 8_200.0),
        (0.38, 0.94),
        (2_800.0, 15_000.0),
        (120.0, 12_500.0),
        (0.06, 0.88),
        (-0.78, 0.54),
        (2.0, 38.0),
        (2, 10),
        (0.08, 4.8),
        (0.0, 0.42),
        (0.38, 0.9),
        (0.06, 0.6),
        (230.0, 1_750.0),
        (0.08, 0.74),
    ),
    "motion_textures": _Family(
        (
            "Pulsing Constellation",
            "Breathing Circuit",
            "Rotating Glass",
            "Tidal Sequence",
            "Granular Footprints",
            "Magnetic Rain",
            "Clockwork Mist",
            "Shifting Sandwave",
            "Helix Current",
            "Flicker Engine",
            "Elastic Orbit",
            "Quantum Ripples",
        ),
        (103, 96, 99, 96, 102, 98, 101, 103, 102, 96, 103, 99),
        (("pulse", "noise"), ("wavetable", "saw"), ("metal", "triangle"), ("square", "vocal")),
        ("bandpass", "notch", "lowpass", "highpass"),
        (55.0, 1_900.0),
        (320.0, 4_500.0),
        (0.28, 0.92),
        (620.0, 7_800.0),
        (180.0, 14_500.0),
        (0.18, 0.92),
        (-0.86, 0.9),
        (3.0, 42.0),
        (2, 12),
        (0.3, 10.5),
        (0.03, 0.64),
        (0.12, 0.76),
        (0.16, 0.7),
        (65.0, 1_300.0),
        (0.22, 0.86),
    ),
    "cinematic": _Family(
        (
            "Heroic Horizon",
            "Tension Wire",
            "Dark Arrival",
            "Wonder Theme",
            "Low Brass Omen",
            "Rising Embers",
            "Suspense Pulse",
            "Memory Montage",
            "Titan Chords",
            "Mystery Chamber",
            "Final Ascent",
            "End Credits Glow",
        ),
        (55, 100, 87, 88, 61, 97, 101, 89, 62, 99, 104, 89),
        (("saw", "organ"), ("vocal", "noise"), ("triangle", "metal"), ("wavetable", "sine")),
        ("lowpass", "bandpass", "highpass", "notch"),
        (18.0, 2_800.0),
        (420.0, 5_800.0),
        (0.34, 0.98),
        (900.0, 12_500.0),
        (90.0, 13_000.0),
        (0.12, 0.9),
        (-0.72, 0.86),
        (1.0, 40.0),
        (2, 12),
        (0.12, 7.2),
        (0.01, 0.54),
        (0.28, 0.88),
        (0.04, 0.58),
        (110.0, 1_500.0),
        (0.08, 0.78),
    ),
}


def _fraction(index: int, salt: int) -> float:
    """A tiny deterministic low-discrepancy sequence for musical variation."""

    return ((index * (31 + salt * 2) + salt * 17) % 101) / 100.0


def _between(bounds: tuple[float, float], index: int, salt: int) -> float:
    low, high = bounds
    return round(low + (high - low) * _fraction(index, salt), 4)


def _voice_count(bounds: tuple[int, int], index: int) -> int:
    low, high = bounds
    return low + ((index * 3 + 1) % (high - low + 1))


def _build_catalog() -> tuple[Preset, ...]:
    presets: list[Preset] = []
    program_id = 0
    for category in CATEGORIES:
        family = _FAMILIES[category]
        for index, name in enumerate(family.names):
            waveform_a, waveform_b = family.wave_pairs[index % len(family.wave_pairs)]
            presets.append(
                Preset(
                    program_id=program_id,
                    midi_program=family.midi_programs[index],
                    category=category,
                    name=name,
                    waveform_a=waveform_a,
                    waveform_b=waveform_b,
                    waveform_mix=_between((0.12, 0.88), index, 1),
                    attack_ms=_between(family.attack, index, 2),
                    decay_ms=_between(family.decay, index, 3),
                    sustain=_between(family.sustain, index, 4),
                    release_ms=_between(family.release, index, 5),
                    filter_type=family.filter_types[index % len(family.filter_types)],
                    filter_cutoff_hz=_between(family.cutoff, index, 6),
                    filter_resonance=_between(family.resonance, index, 7),
                    filter_envelope=_between(family.filter_envelope, index, 8),
                    detune_cents=_between(family.detune, index, 9),
                    unison_voices=_voice_count(family.unison, index),
                    vibrato_rate_hz=_between(family.vibrato_rate, index, 10),
                    vibrato_depth_semitones=_between(family.vibrato_depth, index, 11),
                    reverb_mix=_between(family.reverb, index, 12),
                    delay_mix=_between(family.delay, index, 13),
                    delay_time_ms=_between(family.delay_time, index, 14),
                    chorus_mix=_between(family.chorus, index, 15),
                )
            )
            program_id += 1
    return tuple(presets)


def validate_catalog(presets: Iterable[Preset]) -> None:
    """Validate preset objects and enforce identity and sound-design uniqueness."""

    catalog = tuple(presets)
    if not catalog:
        raise ValueError("preset catalog must not be empty")
    for preset in catalog:
        preset.validate()

    ids = [preset.program_id for preset in catalog]
    names = [preset.name.casefold() for preset in catalog]
    signatures = [preset.synthesis_signature for preset in catalog]
    if len(ids) != len(set(ids)):
        raise ValueError("preset program IDs must be unique")
    if len(names) != len(set(names)):
        raise ValueError("preset names must be unique")
    if len(signatures) != len(set(signatures)):
        raise ValueError("presets must not alias the same synthesis parameters")


PRESETS = _build_catalog()
validate_catalog(PRESETS)

PRESETS_BY_ID = MappingProxyType({preset.program_id: preset for preset in PRESETS})


def _normalize_label(label: str) -> str:
    if not isinstance(label, str):
        raise TypeError("preset labels must be strings")
    return " ".join(label.replace("_", " ").replace("-", " ").split()).casefold()


PRESETS_BY_NAME = MappingProxyType({_normalize_label(preset.name): preset for preset in PRESETS})

_CATEGORY_ALIASES = {
    _normalize_label(category): category for category in CATEGORIES
} | {
    _normalize_label(category.removesuffix("s")): category for category in CATEGORIES
}
_CATEGORY_ALIASES["motion texture"] = "motion_textures"


def category_names() -> tuple[str, ...]:
    """Return canonical category names in stable catalog order."""

    return CATEGORIES


def get_preset(program_id: int) -> Preset:
    """Look up a preset by its stable program ID."""

    try:
        return PRESETS_BY_ID[program_id]
    except KeyError:
        raise KeyError(f"unknown preset program ID: {program_id}") from None


def get_preset_by_name(name: str) -> Preset:
    """Look up a preset by a case- and separator-insensitive display name."""

    normalized = _normalize_label(name)
    try:
        return PRESETS_BY_NAME[normalized]
    except KeyError:
        raise KeyError(f"unknown preset name: {name!r}") from None


def presets_by_category(category: str) -> tuple[Preset, ...]:
    """Return one category in program order, accepting singular display names."""

    normalized = _normalize_label(category)
    try:
        canonical = _CATEGORY_ALIASES[normalized]
    except KeyError:
        raise KeyError(f"unknown preset category: {category!r}") from None
    return tuple(preset for preset in PRESETS if preset.category == canonical)


def preset_names(category: str | None = None) -> tuple[str, ...]:
    """Return all display names, or the names within a requested category."""

    presets = PRESETS if category is None else presets_by_category(category)
    return tuple(preset.name for preset in presets)


# Friendly aliases for renderers that prefer catalog terminology.
PRESET_CATALOG = PRESETS
CATALOG = PRESETS
find_preset = get_preset_by_name
