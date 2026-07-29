#include "sample_timeline.h"

#include "sammyblaze/audio_core/presets.h"
#include "sammyblaze/audio_core/synth_engine.h"

#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <new>

namespace Core = ::SammyBlaze::AudioCore;
namespace Timeline = ::Steinberg::Vst::SammyBlaze::SampleTimeline;

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

enum class ActionType : std::uint8_t
{
    noteOn,
    masterGain,
};

struct Action
{
    std::int32_t sampleOffset {0};
    ActionType type {ActionType::noteOn};
    float value {0.0f};
};

struct Segment
{
    std::int32_t sampleOffset {0};
    std::int32_t frames {0};
};

bool configure (
    Core::SynthEngine& engine,
    float masterGain)
{
    auto patch = Core::presetForProgram (0);
    patch.waveformA = Core::Waveform::sine;
    patch.waveformB = Core::Waveform::sine;
    patch.waveformMix = 0.0f;
    patch.attackMs = 0.0f;
    patch.decayMs = 0.5f;
    patch.sustain = 1.0f;
    patch.releaseMs = 0.5f;
    patch.filterType = Core::FilterType::lowpass;
    patch.filterCutoffHz = 18000.0f;
    patch.filterResonance = 0.0f;
    patch.filterEnvelope = 0.0f;
    patch.unisonVoices = 1;
    patch.vibratoRateHz = 0.0f;
    patch.vibratoDepthSemitones = 0.0f;
    patch.reverbMix = 0.0f;
    patch.delayMix = 0.0f;
    patch.chorusMix = 0.0f;
    return engine.applyPatch (patch, masterGain, 0.5f) &&
           engine.setup (48000.0, 256);
}

template <std::size_t ActionCount, std::size_t FrameCount>
bool runTimeline (
    Core::SynthEngine& engine,
    const std::array<Action, ActionCount>& actions,
    std::array<float, FrameCount>& left,
    std::array<float, FrameCount>& right,
    std::array<Segment, 4>* segments = nullptr,
    std::size_t* segmentCount = nullptr)
{
    std::size_t actionIndex = 0;
    auto peek = [&] (std::int32_t, std::int32_t) {
        if (actionIndex >= actions.size ())
            return Timeline::NextAction {};
        return Timeline::NextAction {
            actions[actionIndex].sampleOffset,
            true,
        };
    };
    auto apply = [&] (std::int32_t sampleOffset) {
        while (actionIndex < actions.size () &&
               actions[actionIndex].sampleOffset == sampleOffset)
        {
            const auto& action = actions[actionIndex++];
            if (action.type == ActionType::noteOn)
                engine.noteOn (60, action.value);
            else
                engine.setMasterGain (action.value);
        }
        return true;
    };
    auto render = [&] (std::int32_t sampleOffset, std::int32_t frames) {
        if (segments && segmentCount &&
            *segmentCount < segments->size ())
        {
            (*segments)[(*segmentCount)++] = {sampleOffset, frames};
        }
        return engine.renderPlanar (
            left.data () + sampleOffset,
            right.data () + sampleOffset,
            static_cast<std::uint32_t> (frames));
    };
    return Timeline::render (
        static_cast<std::int32_t> (FrameCount),
        peek,
        apply,
        render);
}

template <std::size_t Size>
bool silentRange (
    const std::array<float, Size>& output,
    std::size_t first,
    std::size_t last)
{
    for (auto index = first; index < last; ++index)
    {
        if (output[index] != 0.0f)
            return false;
    }
    return true;
}

template <std::size_t Size>
float energy (
    const std::array<float, Size>& output,
    std::size_t first,
    std::size_t last)
{
    float sum = 0.0f;
    for (auto index = first; index < last; ++index)
        sum += output[index] * output[index];
    return sum;
}

bool validateNoteOffset ()
{
    Core::SynthEngine engine;
    if (!configure (engine, 0.8f))
        return false;

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    constexpr std::array<Action, 1> actions {{
        {37, ActionType::noteOn, 1.0f},
    }};
    std::array<Segment, 4> segments {};
    std::size_t segmentCount = 0;
    if (!runTimeline (
            engine,
            actions,
            left,
            right,
            &segments,
            &segmentCount))
        return false;
    if (segmentCount != 2 ||
        segments[0].sampleOffset != 0 ||
        segments[0].frames != 37 ||
        segments[1].sampleOffset != 37 ||
        segments[1].frames != 91 ||
        !silentRange (left, 0, 37) ||
        energy (left, 37, left.size ()) <= 0.000001f)
    {
        std::cerr << "note-on did not begin exactly at sample 37\n";
        return false;
    }
    return true;
}

bool validateAutomationOffset ()
{
    Core::SynthEngine engine;
    if (!configure (engine, 0.0f))
        return false;
    engine.noteOn (60, 1.0f);

    std::array<float, 128> left {};
    std::array<float, 128> right {};
    constexpr std::array<Action, 1> actions {{
        {53, ActionType::masterGain, 1.0f},
    }};
    if (!runTimeline (engine, actions, left, right) ||
        !silentRange (left, 0, 53) ||
        energy (left, 53, left.size ()) <= 0.0000001f)
    {
        std::cerr << "gain automation did not begin exactly at sample 53\n";
        return false;
    }
    return true;
}

bool validateAllocationFreeTimeline ()
{
    Core::SynthEngine engine;
    if (!configure (engine, 0.7f))
        return false;
    engine.noteOn (60, 1.0f);
    std::array<float, 256> left {};
    std::array<float, 256> right {};
    constexpr std::array<Action, 1> actions {{
        {128, ActionType::masterGain, 0.7f},
    }};
    for (int block = 0; block < 32; ++block)
    {
        if (!runTimeline (engine, actions, left, right))
            return false;
    }
    const auto before =
        allocationCount.load (std::memory_order_relaxed);
    for (int block = 0; block < 1000; ++block)
    {
        if (!runTimeline (engine, actions, left, right))
            return false;
    }
    const auto after =
        allocationCount.load (std::memory_order_relaxed);
    if (after != before)
    {
        std::cerr << "sample timeline allocated "
                  << (after - before) << " times\n";
        return false;
    }
    return true;
}

} // namespace

int main ()
{
    if (!validateNoteOffset () ||
        !validateAutomationOffset () ||
        !validateAllocationFreeTimeline ())
        return 1;
    std::cout << "PASS: sample-accurate note/automation ranges and "
                 "zero-allocation segmented rendering\n";
    return 0;
}
