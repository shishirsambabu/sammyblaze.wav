#include "dsp.h"
#include "presets.h"

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>

namespace SammyBlaze = Steinberg::Vst::SammyBlaze;

namespace {

constexpr double twoPi = 6.28318530717958647692;

bool validatePreset (
    const SammyBlaze::SynthPreset& preset,
    double sampleRate,
    float brightness,
    float& maximumMagnitude)
{
    float low = 0.0f;
    float band = 0.0f;
    const auto sampleCount = static_cast<std::size_t> (
        std::min (sampleRate * 0.35, 24000.0));

    for (std::size_t sample = 0; sample < sampleCount; ++sample)
    {
        const auto phase =
            static_cast<double> (sample) * 440.0 / sampleRate;
        const auto excitation =
            static_cast<float> (
                std::sin (phase * twoPi) * 0.72 +
                std::sin (phase * twoPi * 2.417) * 0.23) +
            (sample % 997 == 0 ? 0.5f : 0.0f);
        const auto envelope =
            static_cast<float> (sample % 4096) / 4095.0f;
        const auto cutoff = SammyBlaze::effectiveFilterCutoff (
            preset.filterCutoffHz,
            preset.filterEnvelope,
            envelope,
            brightness,
            sampleRate);
        const auto frame = SammyBlaze::processStateVariableFilter (
            excitation,
            cutoff,
            preset.filterResonance,
            sampleRate,
            low,
            band);
        const auto output =
            SammyBlaze::selectFilterOutput (frame, preset.filterType);
        if (!std::isfinite (output) || !std::isfinite (low) ||
            !std::isfinite (band))
        {
            std::cerr << "non-finite factory render: program "
                      << static_cast<int> (preset.program) << " ("
                      << preset.name << "), sample rate " << sampleRate
                      << ", brightness " << brightness << '\n';
            return false;
        }
        maximumMagnitude =
            std::max (maximumMagnitude, std::abs (output));
    }
    return true;
}

bool validateStabilityBoundary ()
{
    constexpr std::array<float, 5> resonances {0.0f, 0.25f, 0.5f, 0.75f, 1.0f};
    constexpr std::array<float, 5> cutoffRatios {0.001f, 0.08f, 0.18f, 0.31f, 0.42f};
    constexpr double sampleRate = 48000.0;

    for (const auto resonance : resonances)
    {
        const auto damping = SammyBlaze::filterDamping (resonance);
        for (const auto ratio : cutoffRatios)
        {
            const auto coefficient =
                SammyBlaze::stateVariableFilterCoefficient (
                    static_cast<float> (sampleRate) * ratio,
                    resonance,
                    sampleRate);
            if (!(coefficient * coefficient +
                      2.0f * damping * coefficient <
                  4.0f))
            {
                std::cerr << "filter coefficient crossed stability boundary: resonance "
                          << resonance << ", cutoff ratio " << ratio << '\n';
                return false;
            }

            float low = 0.0f;
            float band = 0.0f;
            std::uint32_t noise = 0x9e3779b9U;
            for (std::size_t sample = 0; sample < 48000; ++sample)
            {
                noise = noise * 1664525U + 1013904223U;
                const auto excitation =
                    static_cast<float> ((noise >> 8U) & 0x00FFFFFFU) /
                        static_cast<float> (0x007FFFFFU) -
                    1.0f;
                const auto frame = SammyBlaze::processStateVariableFilter (
                    excitation,
                    static_cast<float> (sampleRate) * ratio,
                    resonance,
                    sampleRate,
                    low,
                    band);
                if (!std::isfinite (frame.low) ||
                    !std::isfinite (frame.high) ||
                    !std::isfinite (frame.band) ||
                    !std::isfinite (frame.notch))
                {
                    std::cerr << "non-finite adversarial render: resonance "
                              << resonance << ", cutoff ratio " << ratio << '\n';
                    return false;
                }
            }
        }
    }
    return true;
}

bool validateNonFiniteContainment ()
{
    float low = std::numeric_limits<float>::infinity ();
    float band = std::numeric_limits<float>::quiet_NaN ();
    const auto frame = SammyBlaze::processStateVariableFilter (
        std::numeric_limits<float>::quiet_NaN (),
        std::numeric_limits<float>::infinity (),
        std::numeric_limits<float>::quiet_NaN (),
        std::numeric_limits<double>::quiet_NaN (),
        low,
        band);
    return std::isfinite (frame.low) && std::isfinite (frame.high) &&
           std::isfinite (frame.band) && std::isfinite (frame.notch) &&
           std::isfinite (low) && std::isfinite (band);
}

std::size_t countLegacyUnsafeFactoryScenarios ()
{
    constexpr std::array<double, 5> sampleRates {
        32000.0, 44100.0, 48000.0, 96000.0, 192000.0};
    std::size_t unsafe = 0;
    for (std::size_t program = 0; program < SammyBlaze::kPresetCount; ++program)
    {
        const auto preset =
            SammyBlaze::presetForProgram (static_cast<std::uint8_t> (program));
        const auto damping = SammyBlaze::filterDamping (preset.filterResonance);
        for (const auto sampleRate : sampleRates)
        {
            const auto cutoff = SammyBlaze::effectiveFilterCutoff (
                preset.filterCutoffHz,
                preset.filterEnvelope,
                1.0f,
                1.0f,
                sampleRate);
            const auto legacyCoefficient = std::clamp (
                2.0f * std::sin (
                    SammyBlaze::kPi * cutoff / static_cast<float> (sampleRate)),
                SammyBlaze::kMinimumFilterCoefficient,
                SammyBlaze::kLegacyFilterCoefficientLimit);
            if (legacyCoefficient * legacyCoefficient +
                    2.0f * damping * legacyCoefficient >=
                4.0f)
                ++unsafe;
        }
    }
    return unsafe;
}

} // namespace

int main ()
{
    constexpr std::array<double, 5> sampleRates {
        32000.0, 44100.0, 48000.0, 96000.0, 192000.0};
    constexpr std::array<float, 3> brightnessValues {0.0f, 0.5f, 1.0f};

    float maximumMagnitude = 0.0f;
    std::size_t renderedScenarios = 0;
    for (std::size_t program = 0; program < SammyBlaze::kPresetCount; ++program)
    {
        const auto preset =
            SammyBlaze::presetForProgram (static_cast<std::uint8_t> (program));
        if (preset.program != program || preset.name == nullptr ||
            !std::isfinite (preset.filterCutoffHz) ||
            !std::isfinite (preset.filterResonance) ||
            !std::isfinite (preset.filterEnvelope))
        {
            std::cerr << "invalid factory preset contract at program "
                      << program << '\n';
            return 1;
        }
        for (const auto sampleRate : sampleRates)
        {
            for (const auto brightness : brightnessValues)
            {
                if (!validatePreset (
                        preset,
                        sampleRate,
                        brightness,
                        maximumMagnitude))
                    return 1;
                ++renderedScenarios;
            }
        }
    }

    if (!validateStabilityBoundary ())
        return 1;
    if (!validateNonFiniteContainment ())
    {
        std::cerr << "non-finite containment did not recover filter state\n";
        return 1;
    }

    const auto legacyUnsafeScenarios = countLegacyUnsafeFactoryScenarios ();
    if (legacyUnsafeScenarios == 0)
    {
        std::cerr << "validation fixture did not cover the legacy instability\n";
        return 1;
    }

    std::cout << "PASS: " << SammyBlaze::kPresetCount
              << " factory programs, " << renderedScenarios
              << " rate/brightness renders, stability stress, finite output\n"
              << "Legacy coefficient would cross the stability boundary in "
              << legacyUnsafeScenarios << " covered factory scenarios\n"
              << "Maximum validated filter magnitude: " << maximumMagnitude
              << '\n';
    return 0;
}
