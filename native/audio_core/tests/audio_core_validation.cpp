#include "sammyblaze/audio_core/presets.h"
#include "sammyblaze/audio_core/synth_engine.h"

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

bool validateAllocationFreeRendering ()
{
    Core::SynthEngine engine;
    std::array<float, 512> output {};
    if (!engine.setup (48000.0, 256))
        return false;
    engine.programChange (107);
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
        !validateAllocationFreeRendering () ||
        !validateEngineArguments ())
        return 1;
    std::cout << "PASS: shared SynthEngine finite, allocation-free, "
                 "24-voice, sustain and panic validation\n";
    return 0;
}
