#include "sammyblaze/audio_core/presets.h"

#include <array>
#include <utility>

namespace SammyBlaze::AudioCore {
namespace {

using Bounds = std::pair<float, float>;
using WavePair = std::pair<Waveform, Waveform>;

struct Family
{
    std::array<WavePair, 4> waves;
    std::size_t waveCount;
    std::array<FilterType, 4> filters;
    std::size_t filterCount;
    Bounds attack;
    Bounds decay;
    Bounds sustain;
    Bounds release;
    Bounds cutoff;
    Bounds resonance;
    Bounds filterEnvelope;
    Bounds detune;
    std::pair<int, int> unison;
    Bounds vibratoRate;
    Bounds vibratoDepth;
    Bounds reverb;
    Bounds delay;
    Bounds delayTime;
    Bounds chorus;
};

constexpr std::array<const char*, kPresetCount> names {{
    "Studio Grand", "Velvet Upright", "Glass Rhodes", "Midnight Tines",
    "Copper Wurlitzer", "Tape Pianette", "Neon Clavinet", "Soft Felt Keys",
    "Chorus Electric Piano", "Crystal Harpsichord", "Lo-Fi Keybed", "Celestial Keys",
    "Sub Monarch", "Rubber Current", "Analog Anchor", "Acid Prowler",
    "Electric Pulse Bass", "FM Quarry", "Reese Horizon", "Plucked Lowline",
    "Darkside Bass", "Growl Circuit", "Voltage Bass", "Cinematic Sub",
    "Solar Monosynth", "Singing Square", "Razor Ribbon", "Portamento Glass",
    "Aurora Lead", "Brassfire Solo", "Pulse Voyager", "Harmonic Flute",
    "Electric Soprano", "Sync Serpent", "Dreamcaster Lead", "Arena Anthem",
    "Walnut Pluck", "Digital Koto", "Prism Marimba", "Rubber Kalimba",
    "Sequencer Pick", "Frosted String", "Neon Droplet", "Muted Circuit",
    "Sunlit Pizzicato", "Bamboo Pulse", "Elastic Harp", "Stardust Pluck",
    "Silver Handbell", "FM Temple Bell", "Glass Carillon", "Ice Celesta",
    "Bronze Halo", "Music Box Moon", "Crystal Chime", "Tubular Dawn",
    "Digital Gamelan", "Shimmer Bell", "Broken Toy Bell", "Deep Space Bell",
    "Classic Poly Eight", "Satin Poly", "Brass Matrix", "Vintage Pulse Stack",
    "Neon Poly Chord", "Sync Panorama", "Soft Analog Ensemble", "Digital Superstack",
    "Warm Saw Choir", "Prism Poly", "Retro Film Synth", "Wide Horizon Poly",
    "Warm Cloud Pad", "Velvet Strings Pad", "Lunar Choir Pad", "Analog Sunrise",
    "Frozen Glass Pad", "Oceanic Pad", "Ember Pad", "Slow Brass Canopy",
    "Dream Tape Pad", "Cathedral Air Pad", "Aurora String Pad", "Infinite Bloom Pad",
    "Distant Rainlight", "Orbital Dust", "Empty Cathedral", "Underwater Signals",
    "Polar Night Air", "Forest Haze", "Radio Nebula", "Desert Stars",
    "Glass Horizon", "Subterranean Wind", "Cloud Chamber", "Afterglow Field",
    "Pulsing Constellation", "Breathing Circuit", "Rotating Glass", "Tidal Sequence",
    "Granular Footprints", "Magnetic Rain", "Clockwork Mist", "Shifting Sandwave",
    "Helix Current", "Flicker Engine", "Elastic Orbit", "Quantum Ripples",
    "Heroic Horizon", "Tension Wire", "Dark Arrival", "Wonder Theme",
    "Low Brass Omen", "Rising Embers", "Suspense Pulse", "Memory Montage",
    "Titan Chords", "Mystery Chamber", "Final Ascent", "End Credits Glow",
}};

constexpr WavePair wp (Waveform a, Waveform b)
{
    return {a, b};
}

constexpr std::array<Family, 10> families {{
    {
        {wp (Waveform::triangle, Waveform::sine), wp (Waveform::sine, Waveform::metal),
         wp (Waveform::triangle, Waveform::organ), wp (Waveform::triangle, Waveform::sine)},
        3,
        {FilterType::lowpass, FilterType::bandpass, FilterType::lowpass,
         FilterType::lowpass},
        2,
        {2.0f, 55.0f}, {180.0f, 1600.0f}, {0.22f, 0.78f}, {180.0f, 2400.0f},
        {1600.0f, 12000.0f}, {0.05f, 0.46f}, {-0.12f, 0.48f}, {0.0f, 9.0f},
        {1, 4}, {3.8f, 6.2f}, {0.0f, 0.18f}, {0.04f, 0.42f}, {0.0f, 0.24f},
        {90.0f, 520.0f}, {0.0f, 0.38f},
    },
    {
        {wp (Waveform::sine, Waveform::saw), wp (Waveform::triangle, Waveform::square),
         wp (Waveform::saw, Waveform::pulse), wp (Waveform::sine, Waveform::metal)},
        4,
        {FilterType::lowpass, FilterType::bandpass, FilterType::lowpass,
         FilterType::lowpass},
        2,
        {1.0f, 35.0f}, {80.0f, 760.0f}, {0.42f, 0.98f}, {55.0f, 620.0f},
        {90.0f, 3800.0f}, {0.12f, 0.82f}, {-0.18f, 0.72f}, {0.0f, 24.0f},
        {1, 6}, {3.0f, 6.8f}, {0.0f, 0.16f}, {0.0f, 0.22f}, {0.0f, 0.2f},
        {65.0f, 390.0f}, {0.0f, 0.34f},
    },
    {
        {wp (Waveform::saw, Waveform::square), wp (Waveform::pulse, Waveform::triangle),
         wp (Waveform::sine, Waveform::vocal), wp (Waveform::saw, Waveform::metal)},
        4,
        {FilterType::lowpass, FilterType::bandpass, FilterType::highpass,
         FilterType::lowpass},
        3,
        {2.0f, 95.0f}, {90.0f, 820.0f}, {0.58f, 1.0f}, {90.0f, 1050.0f},
        {700.0f, 14000.0f}, {0.08f, 0.72f}, {-0.12f, 0.66f}, {0.0f, 28.0f},
        {1, 8}, {4.1f, 7.8f}, {0.08f, 0.72f}, {0.04f, 0.52f}, {0.02f, 0.46f},
        {80.0f, 690.0f}, {0.0f, 0.48f},
    },
    {
        {wp (Waveform::triangle, Waveform::saw), wp (Waveform::sine, Waveform::metal),
         wp (Waveform::square, Waveform::noise), wp (Waveform::sine, Waveform::pulse)},
        4,
        {FilterType::lowpass, FilterType::bandpass, FilterType::highpass,
         FilterType::lowpass},
        3,
        {0.0f, 14.0f}, {55.0f, 920.0f}, {0.0f, 0.26f}, {45.0f, 1300.0f},
        {550.0f, 15000.0f}, {0.04f, 0.72f}, {0.18f, 0.92f}, {0.0f, 15.0f},
        {1, 5}, {3.2f, 7.2f}, {0.0f, 0.12f}, {0.02f, 0.46f}, {0.0f, 0.4f},
        {55.0f, 480.0f}, {0.0f, 0.3f},
    },
    {
        {wp (Waveform::sine, Waveform::metal), wp (Waveform::triangle, Waveform::metal),
         wp (Waveform::sine, Waveform::noise), wp (Waveform::sine, Waveform::metal)},
        3,
        {FilterType::bandpass, FilterType::highpass, FilterType::lowpass,
         FilterType::lowpass},
        3,
        {0.0f, 12.0f}, {380.0f, 4800.0f}, {0.0f, 0.14f}, {520.0f, 7500.0f},
        {1100.0f, 17500.0f}, {0.08f, 0.76f}, {-0.08f, 0.45f}, {0.0f, 11.0f},
        {1, 5}, {4.0f, 8.8f}, {0.0f, 0.22f}, {0.18f, 0.72f}, {0.02f, 0.46f},
        {120.0f, 920.0f}, {0.0f, 0.42f},
    },
    {
        {wp (Waveform::saw, Waveform::pulse), wp (Waveform::square, Waveform::triangle),
         wp (Waveform::saw, Waveform::organ), wp (Waveform::pulse, Waveform::wavetable)},
        4,
        {FilterType::lowpass, FilterType::bandpass, FilterType::notch,
         FilterType::lowpass},
        3,
        {4.0f, 110.0f}, {130.0f, 1350.0f}, {0.42f, 0.96f}, {170.0f, 2100.0f},
        {480.0f, 13500.0f}, {0.08f, 0.68f}, {-0.16f, 0.72f}, {2.0f, 32.0f},
        {2, 10}, {3.4f, 7.1f}, {0.0f, 0.28f}, {0.04f, 0.46f}, {0.0f, 0.38f},
        {80.0f, 610.0f}, {0.04f, 0.64f},
    },
    {
        {wp (Waveform::saw, Waveform::vocal), wp (Waveform::triangle, Waveform::organ),
         wp (Waveform::wavetable, Waveform::sine), wp (Waveform::saw, Waveform::noise)},
        4,
        {FilterType::lowpass, FilterType::bandpass, FilterType::notch,
         FilterType::lowpass},
        3,
        {280.0f, 4600.0f}, {650.0f, 5600.0f}, {0.54f, 1.0f}, {1300.0f, 11000.0f},
        {240.0f, 9500.0f}, {0.04f, 0.58f}, {-0.34f, 0.44f}, {5.0f, 46.0f},
        {3, 12}, {0.18f, 5.8f}, {0.02f, 0.46f}, {0.22f, 0.78f}, {0.0f, 0.42f},
        {140.0f, 1100.0f}, {0.14f, 0.72f},
    },
    {
        {wp (Waveform::noise, Waveform::sine), wp (Waveform::wavetable, Waveform::noise),
         wp (Waveform::vocal, Waveform::metal), wp (Waveform::organ, Waveform::noise)},
        4,
        {FilterType::bandpass, FilterType::highpass, FilterType::lowpass,
         FilterType::notch},
        4,
        {620.0f, 7200.0f}, {1100.0f, 8200.0f}, {0.38f, 0.94f}, {2800.0f, 15000.0f},
        {120.0f, 12500.0f}, {0.06f, 0.88f}, {-0.78f, 0.54f}, {2.0f, 38.0f},
        {2, 10}, {0.08f, 4.8f}, {0.0f, 0.42f}, {0.38f, 0.9f}, {0.06f, 0.6f},
        {230.0f, 1750.0f}, {0.08f, 0.74f},
    },
    {
        {wp (Waveform::pulse, Waveform::noise), wp (Waveform::wavetable, Waveform::saw),
         wp (Waveform::metal, Waveform::triangle), wp (Waveform::square, Waveform::vocal)},
        4,
        {FilterType::bandpass, FilterType::notch, FilterType::lowpass,
         FilterType::highpass},
        4,
        {55.0f, 1900.0f}, {320.0f, 4500.0f}, {0.28f, 0.92f}, {620.0f, 7800.0f},
        {180.0f, 14500.0f}, {0.18f, 0.92f}, {-0.86f, 0.9f}, {3.0f, 42.0f},
        {2, 12}, {0.3f, 10.5f}, {0.03f, 0.64f}, {0.12f, 0.76f}, {0.16f, 0.7f},
        {65.0f, 1300.0f}, {0.22f, 0.86f},
    },
    {
        {wp (Waveform::saw, Waveform::organ), wp (Waveform::vocal, Waveform::noise),
         wp (Waveform::triangle, Waveform::metal), wp (Waveform::wavetable, Waveform::sine)},
        4,
        {FilterType::lowpass, FilterType::bandpass, FilterType::highpass,
         FilterType::notch},
        4,
        {18.0f, 2800.0f}, {420.0f, 5800.0f}, {0.34f, 0.98f}, {900.0f, 12500.0f},
        {90.0f, 13000.0f}, {0.12f, 0.9f}, {-0.72f, 0.86f}, {1.0f, 40.0f},
        {2, 12}, {0.12f, 7.2f}, {0.01f, 0.54f}, {0.28f, 0.88f}, {0.04f, 0.58f},
        {110.0f, 1500.0f}, {0.08f, 0.78f},
    },
}};

float fraction (int index, int salt) noexcept
{
    return static_cast<float> ((index * (31 + salt * 2) + salt * 17) % 101) / 100.0f;
}

float between (Bounds bounds, int index, int salt) noexcept
{
    return bounds.first + (bounds.second - bounds.first) * fraction (index, salt);
}

int voiceCount (std::pair<int, int> bounds, int index) noexcept
{
    return bounds.first + ((index * 3 + 1) % (bounds.second - bounds.first + 1));
}

} // namespace

const char* presetName (std::size_t program) noexcept
{
    return names[program % kPresetCount];
}

SynthPreset presetForProgram (std::uint8_t requestedProgram) noexcept
{
    const auto program = static_cast<std::size_t> (requestedProgram) % kPresetCount;
    const auto category = program / kPresetsPerCategory;
    const auto index = static_cast<int> (program % kPresetsPerCategory);
    const auto& family = families[category];
    const auto& wave = family.waves[static_cast<std::size_t> (index) % family.waveCount];
    return {
        static_cast<std::uint8_t> (program),
        names[program],
        wave.first,
        wave.second,
        between ({0.12f, 0.88f}, index, 1),
        between (family.attack, index, 2),
        between (family.decay, index, 3),
        between (family.sustain, index, 4),
        between (family.release, index, 5),
        family.filters[static_cast<std::size_t> (index) % family.filterCount],
        between (family.cutoff, index, 6),
        between (family.resonance, index, 7),
        between (family.filterEnvelope, index, 8),
        between (family.detune, index, 9),
        static_cast<std::uint8_t> (voiceCount (family.unison, index)),
        between (family.vibratoRate, index, 10),
        between (family.vibratoDepth, index, 11),
        between (family.reverb, index, 12),
        between (family.delay, index, 13),
        between (family.delayTime, index, 14),
        between (family.chorus, index, 15),
    };
}

} // namespace SammyBlaze::AudioCore
