#include "sammyblaze/audio_core/presets.h"
#include "sammyblaze/audio_core/synth_engine.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>

namespace Core = ::SammyBlaze::AudioCore;

namespace {
std::atomic<std::uint64_t> allocationCount {0};
}

void* operator new (std::size_t size)
{
    allocationCount.fetch_add (1, std::memory_order_relaxed);
    if (auto* memory = std::malloc (size))
        return memory;
    throw std::bad_alloc {};
}

void* operator new[] (std::size_t size)
{
    return ::operator new (size);
}

void operator delete (void* memory) noexcept
{
    std::free (memory);
}

void operator delete[] (void* memory) noexcept
{
    std::free (memory);
}

void operator delete (void* memory, std::size_t) noexcept
{
    std::free (memory);
}

void operator delete[] (void* memory, std::size_t) noexcept
{
    std::free (memory);
}

namespace {

bool finiteBuffer (const std::array<float, 512>& output)
{
    for (const auto sample : output)
    {
        if (!std::isfinite (sample))
            return false;
    }
    return true;
}

bool validateFactoryPrograms ()
{
    constexpr std::array<double, 5> sampleRates {
        32000.0, 44100.0, 48000.0, 96000.0, 192000.0};
    std::array<float, 512> output {};
    std::size_t renders = 0;

    for (const auto sampleRate : sampleRates)
    {
        Core::SynthEngine engine;
        if (!engine.setup (sampleRate, 256))
        {
            std::cerr << "setup failed at " << sampleRate << " Hz\n";
            return false;
        }

        for (std::uint32_t program = 0; program < Core::kPresetCount; ++program)
        {
            engine.programChange (static_cast<std::uint8_t> (program));
            engine.noteOn (60, 1.0f);
            for (int block = 0; block < 6; ++block)
            {
                if (!engine.renderInterleaved (output.data (), 256) ||
                    !finiteBuffer (output))
                {
                    std::cerr << "non-finite engine render: program "
                              << program << " at " << sampleRate << " Hz\n";
                    return false;
                }
                ++renders;
            }
            engine.noteOff (60);
            engine.panic ();
        }
        if (engine.nonfiniteRecoveryCount () != 0)
        {
            std::cerr << "unexpected non-finite recovery at "
                      << sampleRate << " Hz\n";
            return false;
        }
    }

    std::cout << "Factory engine renders: " << renders
              << " (120 programs x 5 rates x 6 blocks)\n";
    return true;
}

bool validateVoiceAndSustainSemantics ()
{
    Core::SynthEngine engine;
    std::array<float, 512> output {};
    if (!engine.setup (48000.0, 256))
        return false;

    auto patch = Core::presetForProgram (0);
    patch.attackMs = 0.0f;
    patch.decayMs = 1.0f;
    patch.sustain = 1.0f;
    patch.releaseMs = 1.0f;
    if (!engine.applyPatch (patch, 0.75f, 0.5f))
        return false;

    for (std::uint8_t note = 36; note < 66; ++note)
        engine.noteOn (note, 0.8f);
    if (engine.activeVoiceCount () != Core::kMaximumVoices)
    {
        std::cerr << "voice stealing did not retain exactly 24 voices\n";
        return false;
    }
    engine.panic ();
    if (engine.activeVoiceCount () != 0)
    {
        std::cerr << "panic did not clear voices\n";
        return false;
    }

    engine.noteOn (60, 1.0f);
    engine.controlChange (64, 127);
    engine.noteOff (60);
    for (int block = 0; block < 12; ++block)
        engine.renderInterleaved (output.data (), 256);
    if (engine.activeVoiceCount () != 1)
    {
        std::cerr << "sustain did not hold released key\n";
        return false;
    }
    engine.controlChange (64, 0);
    for (int block = 0; block < 4; ++block)
        engine.renderInterleaved (output.data (), 256);
    if (engine.activeVoiceCount () != 0)
    {
        std::cerr << "sustain release did not finish voice\n";
        return false;
    }
    return true;
}

Core::SynthPreset unisonTestPatch ()
{
    auto patch = Core::presetForProgram (0);
    patch.waveformA = Core::Waveform::sine;
    patch.waveformB = Core::Waveform::sine;
    patch.waveformMix = 0.0f;
    patch.attackMs = 0.0f;
    patch.decayMs = 0.5f;
    patch.sustain = 1.0f;
    patch.releaseMs = 100.0f;
    patch.filterType = Core::FilterType::lowpass;
    patch.filterCutoffHz = 18000.0f;
    patch.filterResonance = 0.0f;
    patch.filterEnvelope = 0.0f;
    patch.detuneCents = 40.0f;
    patch.unisonVoices = 16;
    patch.vibratoRateHz = 0.0f;
    patch.vibratoDepthSemitones = 0.0f;
    patch.reverbMix = 0.0f;
    patch.delayMix = 0.0f;
    patch.chorusMix = 0.0f;
    return patch;
}

bool validateUnisonWorkScaling ()
{
    Core::SynthEngine single;
    Core::SynthEngine sixteen;
    if (!single.setup (48000.0, 256) ||
        !sixteen.setup (48000.0, 256))
        return false;
    auto singlePatch = unisonTestPatch ();
    auto sixteenPatch = singlePatch;
    singlePatch.unisonVoices = 1;
    if (!single.applyPatch (singlePatch, 0.65f, 0.5f) ||
        !sixteen.applyPatch (sixteenPatch, 0.65f, 0.5f))
        return false;
    single.noteOn (60, 0.8f);
    sixteen.noteOn (60, 0.8f);

    std::array<float, 512> singleOutput {};
    std::array<float, 512> sixteenOutput {};
    const auto singleBefore = single.oscillatorWorkCount ();
    const auto sixteenBefore = sixteen.oscillatorWorkCount ();
    if (!single.renderInterleaved (singleOutput.data (), 256) ||
        !sixteen.renderInterleaved (sixteenOutput.data (), 256))
        return false;
    const auto singleWork =
        single.oscillatorWorkCount () - singleBefore;
    const auto sixteenWork =
        sixteen.oscillatorWorkCount () - sixteenBefore;
    if (singleWork != 256 || sixteenWork != 4096 ||
        singleOutput == sixteenOutput ||
        single.requestedUnisonVoices () != 1 ||
        sixteen.requestedUnisonVoices () != 16 ||
        sixteen.renderedUnisonLanesPerVoice () != 16 ||
        sixteen.unisonQualityLimited ())
    {
        std::cerr << "unison 1/16 output or oscillator work is not truthful\n";
        return false;
    }
    return true;
}

bool validateUnisonLevelBounds ()
{
    constexpr std::array<std::uint8_t, 4> noteCounts {1, 6, 12, 24};
    for (const auto noteCount : noteCounts)
    {
        Core::SynthEngine leftEngine;
        Core::SynthEngine rightEngine;
        if (!leftEngine.setup (48000.0, 256) ||
            !rightEngine.setup (48000.0, 256))
            return false;
        const auto patch = unisonTestPatch ();
        if (!leftEngine.applyPatch (patch, 0.65f, 0.5f) ||
            !rightEngine.applyPatch (patch, 0.65f, 0.5f))
            return false;
        for (std::uint8_t note = 0; note < noteCount; ++note)
        {
            leftEngine.noteOn (
                static_cast<std::uint8_t> (48 + note),
                0.72f);
            rightEngine.noteOn (
                static_cast<std::uint8_t> (48 + note),
                0.72f);
        }

        std::array<float, 512> left {};
        std::array<float, 512> right {};
        for (int block = 0; block < 8; ++block)
        {
            if (!leftEngine.renderInterleaved (left.data (), 256) ||
                !rightEngine.renderInterleaved (right.data (), 256) ||
                left != right)
            {
                std::cerr << "unison subset rendering is not deterministic\n";
                return false;
            }
        }

        const auto workBefore = leftEngine.oscillatorWorkCount ();
        double squareSum = 0.0;
        float peak = 0.0f;
        float maximumStep = 0.0f;
        float previous = left[510];
        constexpr int measuredBlocks = 16;
        for (int block = 0; block < measuredBlocks; ++block)
        {
            if (!leftEngine.renderInterleaved (left.data (), 256) ||
                !rightEngine.renderInterleaved (right.data (), 256) ||
                left != right || !finiteBuffer (left))
                return false;
            for (std::size_t sample = 0; sample < 256; ++sample)
            {
                const auto value = left[sample * 2];
                peak = std::max (peak, std::abs (value));
                maximumStep = std::max (
                    maximumStep,
                    std::abs (value - previous));
                squareSum +=
                    static_cast<double> (value) *
                    static_cast<double> (value);
                previous = value;
            }
        }
        const auto rms = std::sqrt (
            squareSum /
            static_cast<double> (measuredBlocks * 256));
        const auto expectedLanes = static_cast<std::uint8_t> (
            std::min<std::size_t> (
                16,
                Core::kUnisonOscillatorBudgetPerSample / noteCount));
        const auto expectedWork =
            static_cast<std::uint64_t> (measuredBlocks) * 256U *
            noteCount * expectedLanes;
        const auto actualWork =
            leftEngine.oscillatorWorkCount () - workBefore;
        if (leftEngine.activeVoiceCount () != noteCount ||
            leftEngine.requestedUnisonVoices () != 16 ||
            leftEngine.renderedUnisonLanesPerVoice () != expectedLanes ||
            leftEngine.unisonQualityLimited () != (expectedLanes < 16) ||
            actualWork != expectedWork ||
            peak <= 0.001f || peak > 0.861f ||
            rms <= 0.0005 || rms > 0.80 ||
            maximumStep > 0.50f)
        {
            std::cerr << "unison level bound failed: notes="
                      << static_cast<int> (noteCount)
                      << " requested=16 effective="
                      << static_cast<int> (
                             leftEngine.renderedUnisonLanesPerVoice ())
                      << " peak=" << peak
                      << " rms=" << rms
                      << " max-step=" << maximumStep << '\n';
            return false;
        }
        std::cout << "Unison levels: notes="
                  << static_cast<int> (noteCount)
                  << " requested=16 effective="
                  << static_cast<int> (expectedLanes)
                  << " peak=" << peak
                  << " rms=" << rms
                  << " max-step=" << maximumStep << '\n';
    }
    return true;
}

bool validateAllocationFreeRendering ()
{
    Core::SynthEngine engine;
    std::array<float, 512> output {};
    if (!engine.setup (48000.0, 256))
        return false;
    auto patch = unisonTestPatch ();
    if (!engine.applyPatch (patch, 0.75f, 0.5f))
        return false;
    for (std::uint8_t note = 36; note < 60; ++note)
        engine.noteOn (note, 0.8f);

    for (int block = 0; block < 32; ++block)
        engine.renderInterleaved (output.data (), 256);
    const auto before = allocationCount.load (std::memory_order_relaxed);
    for (int block = 0; block < 1000; ++block)
    {
        if (!engine.renderInterleaved (output.data (), 256))
            return false;
    }
    const auto after = allocationCount.load (std::memory_order_relaxed);
    if (after != before)
    {
        std::cerr << "render allocated " << (after - before)
                  << " times after setup\n";
        return false;
    }
    std::cout << "Render allocations after setup: 0 across 1,000 blocks\n";
    return true;
}

bool validateEngineArguments ()
{
    Core::SynthEngine engine;
    std::array<float, 512> output {};
    return !engine.setup (
               std::numeric_limits<double>::quiet_NaN (),
               256) &&
           !engine.setup (48000.0, 0) &&
           engine.setup (48000.0, 256) &&
           !engine.renderInterleaved (nullptr, 256) &&
           !engine.renderInterleaved (output.data (), 0) &&
           !engine.renderInterleaved (output.data (), 257);
}

} // namespace

int main ()
{
    if (!validateFactoryPrograms () ||
        !validateVoiceAndSustainSemantics () ||
        !validateUnisonWorkScaling () ||
        !validateUnisonLevelBounds () ||
        !validateAllocationFreeRendering () ||
        !validateEngineArguments ())
        return 1;
    std::cout << "PASS: shared SynthEngine finite, allocation-free, "
                 "24-voice, truthful unison, sustain and panic validation\n";
    return 0;
}
