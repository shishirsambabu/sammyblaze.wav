#pragma once

#include <cstddef>
#include <cstdint>

namespace Steinberg::Vst::SammyBlaze {

enum class Waveform : std::uint8_t
{
    sine,
    triangle,
    saw,
    square,
    pulse,
    organ,
    metal,
    noise,
    vocal,
    wavetable,
};

enum class FilterType : std::uint8_t
{
    lowpass,
    highpass,
    bandpass,
    notch,
};

struct SynthPreset
{
    std::uint8_t program {0};
    const char* name {"Studio Grand"};
    Waveform waveformA {Waveform::triangle};
    Waveform waveformB {Waveform::sine};
    float waveformMix {0.25f};
    float attackMs {20.0f};
    float decayMs {900.0f};
    float sustain {0.6f};
    float releaseMs {2000.0f};
    FilterType filterType {FilterType::lowpass};
    float filterCutoffHz {1700.0f};
    float filterResonance {0.12f};
    float filterEnvelope {0.09f};
    float detuneCents {4.7f};
    std::uint8_t unisonVoices {2};
    float vibratoRateHz {5.4f};
    float vibratoDepthSemitones {0.15f};
    float reverbMix {0.05f};
    float delayMix {0.05f};
    float delayTimeMs {245.0f};
    float chorusMix {0.2f};
};

inline constexpr std::size_t kPresetCount = 120;
inline constexpr std::size_t kPresetsPerCategory = 12;

SynthPreset presetForProgram (std::uint8_t program) noexcept;
const char* presetName (std::size_t program) noexcept;

} // namespace Steinberg::Vst::SammyBlaze
