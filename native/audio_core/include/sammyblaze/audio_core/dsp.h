#pragma once

#include "sammyblaze/audio_core/presets.h"

#include <algorithm>
#include <cmath>

namespace SammyBlaze::AudioCore {

inline constexpr float kMinimumFilterCutoffHz = 25.0f;
inline constexpr float kMaximumFilterNyquistRatio = 0.42f;
inline constexpr float kMinimumFilterCoefficient = 0.001f;
inline constexpr float kLegacyFilterCoefficientLimit = 0.95f;
inline constexpr float kFilterStabilityMargin = 0.95f;
inline constexpr float kPi = 3.14159265358979323846f;

struct StateVariableFilterFrame
{
    float low {0.0f};
    float high {0.0f};
    float band {0.0f};
    float notch {0.0f};
};

inline float finiteOr (float value, float fallback) noexcept
{
    return std::isfinite (value) ? value : fallback;
}

inline double finiteOr (double value, double fallback) noexcept
{
    return std::isfinite (value) ? value : fallback;
}

inline float filterDamping (float resonance) noexcept
{
    const auto safeResonance = std::clamp (finiteOr (resonance, 0.0f), 0.0f, 1.0f);
    return 1.95f - safeResonance * 1.55f;
}

inline float maximumStableFilterCoefficient (float damping) noexcept
{
    const auto safeDamping = std::max (finiteOr (damping, 1.95f), 0.0001f);
    // For the Chamberlin state transition used below, the Jury stability
    // boundary is f^2 + 2*damping*f < 4. Stay below that boundary to absorb
    // floating-point error and sample-to-sample cutoff modulation.
    return kFilterStabilityMargin *
           (std::sqrt (safeDamping * safeDamping + 4.0f) - safeDamping);
}

inline float stateVariableFilterCoefficient (
    float cutoffHz,
    float resonance,
    double sampleRate) noexcept
{
    const auto safeSampleRate = std::max (finiteOr (sampleRate, 44100.0), 1000.0);
    const auto maximumCutoff =
        std::max (kMinimumFilterCutoffHz,
                  static_cast<float> (safeSampleRate) * kMaximumFilterNyquistRatio);
    const auto safeCutoff = std::clamp (
        finiteOr (cutoffHz, kMinimumFilterCutoffHz),
        kMinimumFilterCutoffHz,
        maximumCutoff);
    const auto requested = 2.0f * std::sin (
        kPi * safeCutoff / static_cast<float> (safeSampleRate));
    const auto stableLimit = std::min (
        kLegacyFilterCoefficientLimit,
        maximumStableFilterCoefficient (filterDamping (resonance)));
    return std::clamp (finiteOr (requested, kMinimumFilterCoefficient),
                       kMinimumFilterCoefficient,
                       stableLimit);
}

inline float effectiveFilterCutoff (
    float baseCutoffHz,
    float filterEnvelope,
    float envelope,
    float brightness,
    double sampleRate) noexcept
{
    const auto safeSampleRate = std::max (finiteOr (sampleRate, 44100.0), 1000.0);
    const auto safeBaseCutoff =
        std::max (finiteOr (baseCutoffHz, kMinimumFilterCutoffHz),
                  kMinimumFilterCutoffHz);
    const auto safeFilterEnvelope =
        std::clamp (finiteOr (filterEnvelope, 0.0f), -1.0f, 1.0f);
    const auto safeEnvelope = std::clamp (finiteOr (envelope, 0.0f), 0.0f, 1.0f);
    const auto safeBrightness = std::clamp (finiteOr (brightness, 0.5f), 0.0f, 1.0f);
    const auto octaves =
        safeFilterEnvelope * safeEnvelope * 4.0f + (safeBrightness - 0.5f) * 4.0f;
    const auto requested = safeBaseCutoff * std::pow (2.0f, octaves);
    return std::clamp (
        finiteOr (requested, kMinimumFilterCutoffHz),
        kMinimumFilterCutoffHz,
        static_cast<float> (safeSampleRate) * kMaximumFilterNyquistRatio);
}

inline StateVariableFilterFrame processStateVariableFilter (
    float input,
    float cutoffHz,
    float resonance,
    double sampleRate,
    float& lowState,
    float& bandState,
    bool* recovered = nullptr) noexcept
{
    bool didRecover = false;
    if (!std::isfinite (lowState) || !std::isfinite (bandState))
    {
        lowState = 0.0f;
        bandState = 0.0f;
        didRecover = true;
    }

    const auto safeInput = finiteOr (input, 0.0f);
    didRecover = didRecover || !std::isfinite (input);
    const auto damping = filterDamping (resonance);
    const auto coefficient =
        stateVariableFilterCoefficient (cutoffHz, resonance, sampleRate);
    lowState += coefficient * bandState;
    const auto high = safeInput - lowState - damping * bandState;
    bandState += coefficient * high;

    if (!std::isfinite (lowState) || !std::isfinite (bandState) ||
        !std::isfinite (high))
    {
        lowState = 0.0f;
        bandState = 0.0f;
        if (recovered)
            *recovered = true;
        return {};
    }
    if (recovered)
        *recovered = didRecover;
    return {lowState, high, bandState, lowState + high};
}

inline float selectFilterOutput (
    const StateVariableFilterFrame& frame,
    FilterType type) noexcept
{
    switch (type)
    {
        case FilterType::lowpass: return frame.low;
        case FilterType::highpass: return frame.high;
        case FilterType::bandpass: return frame.band;
        case FilterType::notch: return frame.notch;
    }
    return 0.0f;
}

} // namespace SammyBlaze::AudioCore
