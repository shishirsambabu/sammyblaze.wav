#pragma once

#include <algorithm>
#include <cstdint>

namespace Steinberg::Vst::SammyBlaze::SampleTimeline {

struct NextAction
{
    std::int32_t sampleOffset {0};
    bool pending {false};
};

// The callbacks are templates so the audio thread does not construct
// std::function objects. peek() must report the next unconsumed action and
// apply() must consume every action at the supplied offset.
template <typename Peek, typename Apply, typename Render>
bool render (
    std::int32_t sampleCount,
    Peek&& peek,
    Apply&& apply,
    Render&& renderSegment) noexcept
{
    if (sampleCount < 0)
        return false;

    std::int32_t cursor = 0;
    while (true)
    {
        const auto action = peek (cursor, sampleCount);
        if (!action.pending)
        {
            return cursor == sampleCount ||
                   renderSegment (cursor, sampleCount - cursor);
        }

        const auto actionOffset =
            std::clamp (action.sampleOffset, cursor, sampleCount);
        if (actionOffset > cursor &&
            !renderSegment (cursor, actionOffset - cursor))
            return false;
        if (!apply (actionOffset))
            return false;
        cursor = actionOffset;
    }
}

} // namespace Steinberg::Vst::SammyBlaze::SampleTimeline
