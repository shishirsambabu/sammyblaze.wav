#include "sammyblaze/audio_core/presets.h"
#include "sammyblaze/audio_core/synth_engine.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <vector>

namespace Core = ::SammyBlaze::AudioCore;

int main (int argc, char** argv)
{
    constexpr double sampleRate = 48000.0;
    constexpr std::uint32_t blockSize = 256;
    constexpr int warmupBlocks = 500;
    constexpr int measuredBlocks = 5000;
    constexpr double targetP95Ms = 2.67;
    const auto enforce =
        argc > 1 && std::strcmp (argv[1], "--enforce") == 0;

    Core::SynthEngine engine;
    if (!engine.setup (sampleRate, blockSize))
        return 1;
    auto patch = Core::presetForProgram (107);
    patch.attackMs = 0.0f;
    patch.decayMs = 1.0f;
    patch.sustain = 1.0f;
    patch.releaseMs = 1000.0f;
    patch.waveformA = Core::Waveform::metal;
    patch.waveformB = Core::Waveform::wavetable;
    patch.waveformMix = 0.5f;
    patch.unisonVoices = 16;
    patch.reverbMix = 0.8f;
    patch.delayMix = 0.7f;
    patch.chorusMix = 0.8f;
    if (!engine.applyPatch (patch, 0.75f, 0.8f))
        return 1;
    for (std::uint8_t note = 36; note < 60; ++note)
        engine.noteOn (note, 0.8f);

    std::array<float, blockSize * 2> output {};
    for (int block = 0; block < warmupBlocks; ++block)
        engine.renderInterleaved (output.data (), blockSize);

    std::vector<double> durations;
    durations.resize (measuredBlocks);
    for (int block = 0; block < measuredBlocks; ++block)
    {
        const auto started = std::chrono::steady_clock::now ();
        if (!engine.renderInterleaved (output.data (), blockSize))
            return 1;
        const auto finished = std::chrono::steady_clock::now ();
        durations[static_cast<std::size_t> (block)] =
            std::chrono::duration<double, std::milli> (
                finished - started)
                .count ();
    }

    const auto total =
        std::accumulate (durations.begin (), durations.end (), 0.0);
    std::sort (durations.begin (), durations.end ());
    const auto percentile = [&durations] (double quantile) {
        const auto index = static_cast<std::size_t> (
            std::ceil (
                quantile *
                static_cast<double> (durations.size () - 1)));
        return durations[index];
    };
    const auto mean = total / static_cast<double> (durations.size ());
    const auto p50 = percentile (0.50);
    const auto p95 = percentile (0.95);
    const auto p99 = percentile (0.99);
    const auto maximum = durations.back ();
    const auto audioDeadlineMs =
        static_cast<double> (blockSize) / sampleRate * 1000.0;
    const auto requestedUnison = engine.requestedUnisonVoices ();
    const auto renderedUnison =
        engine.renderedUnisonLanesPerVoice ();
    const auto qualityLimited = engine.unisonQualityLimited ();

    std::cout << std::fixed << std::setprecision (4)
              << "SammyBlaze shared SynthEngine benchmark\n"
              << "Voices: " << engine.activeVoiceCount ()
              << ", frames: " << blockSize
              << ", sample rate: " << sampleRate << " Hz\n"
              << "Unison requested: "
              << static_cast<int> (requestedUnison)
              << ", effective lanes/voice: "
              << static_cast<int> (renderedUnison)
              << ", quality limited: "
              << (qualityLimited ? "yes" : "no") << '\n'
              << "Mean: " << mean << " ms"
              << ", p50: " << p50 << " ms"
              << ", p95: " << p95 << " ms"
              << ", p99: " << p99 << " ms"
              << ", max: " << maximum << " ms\n"
              << "Audio deadline: " << audioDeadlineMs << " ms"
              << ", target p95: " << targetP95Ms << " ms"
              << ", p95 headroom: " << audioDeadlineMs / p95 << "x\n"
              << (p95 <= targetP95Ms ? "PASS" : "NOTICE")
              << ": 24-voice p95 "
              << (p95 <= targetP95Ms ? "meets" : "misses")
              << " the Phase 9.2 target\n";
    const auto truthfulBudget =
        requestedUnison == 16 && renderedUnison == 4 &&
        qualityLimited;
    if (!truthfulBudget)
        std::cerr << "FAIL: expected observable 16-requested/4-effective "
                     "quality budget\n";
    return !truthfulBudget || (enforce && p95 > targetP95Ms) ? 1 : 0;
}
