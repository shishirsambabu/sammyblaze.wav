#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <thread>

namespace Steinberg::Vst::SammyBlaze {

enum class BridgeMessageType : std::uint8_t
{
    noteOn = 1,
    noteOff = 2,
    controlChange = 3,
    panic = 4,
};

struct BridgeMessage
{
    BridgeMessageType type {BridgeMessageType::panic};
    std::uint8_t channel {0};
    std::uint8_t data1 {0};
    std::uint8_t data2 {0};
    std::uint32_t sequence {0};
};

class GestureBridgeReceiver
{
public:
    GestureBridgeReceiver () = default;
    ~GestureBridgeReceiver ();

    GestureBridgeReceiver (const GestureBridgeReceiver&) = delete;
    GestureBridgeReceiver& operator= (const GestureBridgeReceiver&) = delete;

    void start ();
    void stop ();
    bool pop (BridgeMessage& message);

private:
    static constexpr std::size_t queueCapacity = 1024;

    void receiveLoop (std::stop_token stopToken);
    bool push (const BridgeMessage& message);

    std::array<BridgeMessage, queueCapacity> queue {};
    std::atomic<std::size_t> readIndex {0};
    std::atomic<std::size_t> writeIndex {0};
    std::jthread worker;
};

} // namespace Steinberg::Vst::SammyBlaze
